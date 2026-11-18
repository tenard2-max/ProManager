"""5초 감시 루프: 파일 해시 비교 → 파싱 → 스냅샷 → 지표 갱신."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app import config as app_config
from app.config import WATCH_INTERVAL_SEC
from app.history.log import HistoryLog
from app.ini.spec_parser import parse_spec_ini
from app.ini.status_store import StatusStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class WatchState:
    last_sync_at: str | None = None
    next_tick_at: float | None = None
    last_duration_ms: float = 0.0
    last_delay_ms: float = 0.0
    warning: str | None = None
    spec_hash: str | None = None
    status_hash: str | None = None
    agent_online: dict[str, bool] = field(
        default_factory=lambda: {"cursor": False, "grok": False}
    )
    last_heartbeat: dict[str, float] = field(default_factory=dict)


class WatchLoop:
    def __init__(
        self,
        status_store: StatusStore,
        history: HistoryLog,
        *,
        spec_path: Path | None = None,
        status_path: Path | None = None,
        snapshot_dir: Path | None = None,
        interval: float = WATCH_INTERVAL_SEC,
        on_update: Callable[[], None] | None = None,
        heartbeat_checker: Callable[[], dict[str, bool]] | None = None,
        metrics_calculator: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.status_store = status_store
        self.history = history
        self.spec_path = Path(spec_path or app_config.SPEC_PATH)
        self.status_path = Path(status_path or app_config.STATUS_PATH)
        self.snapshot_dir = Path(snapshot_dir or app_config.SNAPSHOT_DIR)
        self.interval = interval
        self.on_update = on_update
        self.heartbeat_checker = heartbeat_checker
        self.metrics_calculator = metrics_calculator
        self.state = WatchState()
        self._task: asyncio.Task | None = None
        self._running = False
        self.latest_metrics: dict[str, Any] = {}
        self.latest_spec: dict[str, Any] | None = None
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._restore_snapshots()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _restore_snapshots(self) -> None:
        status_snap = self.snapshot_dir / "project_status.ini"
        if status_snap.exists() and not self.status_path.exists():
            shutil.copy2(status_snap, self.status_path)
        if self.status_path.exists():
            try:
                self.status_store.load()
            except Exception as exc:  # noqa: BLE001
                self.state.warning = f"상태 복원 실패: {exc}"
                self.history.append(
                    "restore_error", {"error": str(exc)}
                )

    async def _run(self) -> None:
        while self._running:
            started = time.monotonic()
            self.state.next_tick_at = started + self.interval
            try:
                await asyncio.to_thread(self.tick)
            except Exception as exc:  # noqa: BLE001
                self.state.warning = str(exc)
                self.history.append("watch_error", {"error": str(exc)})
            elapsed = time.monotonic() - started
            self.state.last_duration_ms = round(elapsed * 1000, 2)
            delay = max(0.0, elapsed - self.interval)
            if delay > 0:
                self.state.last_delay_ms = round(delay * 1000, 2)
                self.history.append(
                    "watch_delay",
                    {"delay_ms": self.state.last_delay_ms},
                )
            sleep_for = max(0.0, self.interval - elapsed)
            await asyncio.sleep(sleep_for)

    def tick(self) -> dict[str, Any]:
        changed = False
        spec_hash = file_sha256(self.spec_path)
        status_hash = file_sha256(self.status_path)

        if spec_hash != self.state.spec_hash:
            changed = True
            self._handle_spec_change(spec_hash)

        if status_hash != self.state.status_hash:
            # 저장소가 쓴 경우와 외부 수정을 모두 감지
            changed = True
            self._handle_status_change(status_hash)

        if self.heartbeat_checker:
            self.state.agent_online = self.heartbeat_checker()

        if self.metrics_calculator:
            self.latest_metrics = self.metrics_calculator()

        self.state.last_sync_at = _now_iso()
        if changed and self.on_update:
            self.on_update()
        return {
            "changed": changed,
            "last_sync_at": self.state.last_sync_at,
            "warning": self.state.warning,
        }

    def _handle_spec_change(self, new_hash: str | None) -> None:
        if new_hash is None:
            self.state.spec_hash = None
            return
        try:
            doc = parse_spec_ini(self.spec_path, strict=False)
            self.latest_spec = doc.to_dict()
            if doc.errors:
                self.state.warning = "; ".join(doc.errors)
                self.history.append(
                    "spec_validation_error", {"errors": doc.errors}
                )
            else:
                self.state.warning = None
            self._save_snapshot(self.spec_path, "spec.ini")
            self.state.spec_hash = new_hash
            self.history.append(
                "spec_changed",
                {"hash": new_hash, "item_count": len(doc.items)},
            )
        except Exception as exc:  # noqa: BLE001
            self.state.warning = f"spec.ini 파싱 실패: {exc}"
            self.history.append("spec_parse_error", {"error": str(exc)})

    def _handle_status_change(self, new_hash: str | None) -> None:
        if new_hash is None:
            self.state.status_hash = None
            return
        try:
            # 저장소 메모리와 파일 동기화
            text = self.status_path.read_text(encoding="utf-8-sig")
            prev = (
                self.status_store.document.to_dict()
                if self.status_store.document
                else None
            )
            doc = self.status_store.replace_from_external_parse(text)
            self._save_snapshot(self.status_path, "project_status.ini")
            self.state.status_hash = new_hash
            self.state.warning = None
            self.history.append(
                "status_changed",
                {
                    "hash": new_hash,
                    "state_version": doc.meta.get("state_version"),
                    "previous": prev,
                    "current": doc.to_dict(),
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.state.warning = f"project_status.ini 파싱 실패: {exc}"
            self.history.append("status_parse_error", {"error": str(exc)})
            # 마지막 정상 스냅샷 유지 (메모리 doc 유지)

    def _save_snapshot(self, src: Path, name: str) -> None:
        if src.exists():
            shutil.copy2(src, self.snapshot_dir / name)

    def snapshot_public(self) -> dict[str, Any]:
        return {
            "last_sync_at": self.state.last_sync_at,
            "next_refresh_in_sec": max(
                0.0,
                (self.state.next_tick_at or time.monotonic()) - time.monotonic(),
            )
            if self.state.next_tick_at
            else self.interval,
            "last_duration_ms": self.state.last_duration_ms,
            "last_delay_ms": self.state.last_delay_ms,
            "warning": self.state.warning,
            "agent_online": dict(self.state.agent_online),
        }
