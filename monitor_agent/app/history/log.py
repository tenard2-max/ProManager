"""추가 전용(append-only) 이력 JSONL 로그."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app import config as app_config
from app.config import HISTORY_RETENTION_DAYS


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class HistoryLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else Path(app_config.HISTORY_LOG_PATH)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, event_type: str, payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
        record = {
            "ts": _now_iso(),
            "event_type": event_type,
            "payload": payload,
            **extra,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return record

    def read_all(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if limit is not None:
            return records[-limit:]
        return records

    def purge_expired(self, retention_days: int = HISTORY_RETENTION_DAYS) -> int:
        """보관 기간이 지난 레코드를 제거한다. 수정이 아니라 재작성."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        kept: list[str] = []
        removed = 0
        with self._lock:
            if not self.path.exists():
                return 0
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    ts = datetime.fromisoformat(rec["ts"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    kept.append(line)
            self.path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        return removed
