"""주간 토큰(주 사용량) 추적. Cursor / 그록 봇 분리 + 구독 주차/잔여 시간."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app import config as app_config


def _now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _now_iso() -> str:
    return _now_local().isoformat(timespec="seconds")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_now_local().tzinfo)
    return dt.astimezone()


def _default_renews_at() -> str:
    today = _now_local()
    days = (2 - today.weekday()) % 7  # Wed
    if days == 0:
        days = 7
    renew = (today + timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return renew.isoformat(timespec="seconds")


def _format_remain(seconds: float) -> str:
    if seconds <= 0:
        return "갱신 시각 지남"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}일")
    if hours or days:
        parts.append(f"{hours}시간")
    parts.append(f"{minutes}분")
    return " ".join(parts)


class TokenUsageStore:
    """로컬 JSON으로 주간 사용량·구독 주차를 보관한다."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else Path(app_config.DATA_DIR) / "token_usage.json"
        self._lock = threading.RLock()
        self._data: dict[str, Any] = self._default()
        self.load()

    @staticmethod
    def _default() -> dict[str, Any]:
        renews = _default_renews_at()
        renew_dt = _parse_dt(renews) or _now_local()
        period_start = (renew_dt - timedelta(days=28)).isoformat(timespec="seconds")
        return {
            "plan": "Premium",
            "label": "Weekly included usage",
            "renews_at": renews,
            "period_start": period_start,
            "cycle_weeks": 4,
            "weekly_included": 1_000_000,
            "cursor_used": 0,
            "grok_used": 0,
            "updated_at": _now_iso(),
            "source": "local",
        }

    def load(self) -> dict[str, Any]:
        with self._lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    merged = self._default()
                    merged.update({k: v for k, v in raw.items() if v is not None})
                    self._data = merged
                    self._ensure_period_unlocked()
                except (json.JSONDecodeError, OSError):
                    self._data = self._default()
                    self._save_unlocked()
            else:
                self._data = self._default()
                self._save_unlocked()
            return dict(self._data)

    def _ensure_period_unlocked(self) -> None:
        renew_dt = _parse_dt(str(self._data.get("renews_at", "")))
        weeks = max(1, int(self._data.get("cycle_weeks", 4) or 4))
        if renew_dt is None:
            return
        start = _parse_dt(str(self._data.get("period_start", "")))
        if start is None:
            self._data["period_start"] = (
                renew_dt - timedelta(days=7 * weeks)
            ).isoformat(timespec="seconds")

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_iso()
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _cycle_info(self) -> dict[str, Any]:
        now = _now_local()
        weeks = max(1, min(12, int(self._data.get("cycle_weeks", 4) or 4)))
        renew_dt = _parse_dt(str(self._data.get("renews_at", "")))
        start_dt = _parse_dt(str(self._data.get("period_start", "")))

        if renew_dt is None:
            renew_dt = now + timedelta(days=7)
        if start_dt is None or start_dt >= renew_dt:
            start_dt = renew_dt - timedelta(days=7 * weeks)

        total_sec = max(1.0, (renew_dt - start_dt).total_seconds())
        elapsed_sec = min(total_sec, max(0.0, (now - start_dt).total_seconds()))
        remain_sec = max(0.0, (renew_dt - now).total_seconds())
        remain_pct = round(100.0 * remain_sec / total_sec, 1)
        elapsed_pct = round(100.0 - remain_pct, 1)

        # 주차: 기간을 N등분. 갱신 직후/경계는 마지막 주로 clamp
        week_len = total_sec / weeks
        raw_week = int(elapsed_sec // week_len) + 1 if elapsed_sec < total_sec else weeks
        current_week = max(1, min(weeks, raw_week))

        week_marks = []
        for i in range(1, weeks + 1):
            week_marks.append(
                {
                    "week": i,
                    "label": f"{i}주차",
                    "active": i == current_week,
                    "done": i < current_week,
                }
            )

        renews_display = renew_dt.strftime("%Y-%m-%d %H:%M")
        return {
            "cycle_weeks": weeks,
            "period_start": start_dt.isoformat(timespec="seconds"),
            "renews_at": renew_dt.isoformat(timespec="seconds"),
            "renews_display": renews_display,
            "renews_label": f"다음 갱신 {renews_display}",
            "current_week": current_week,
            "week_label": f"{current_week}/{weeks}주차",
            "weeks": week_marks,
            "remain_seconds": int(remain_sec),
            "remain_display": _format_remain(remain_sec),
            "remain_pct": remain_pct,
            "elapsed_pct": elapsed_pct,
        }

    def reload_if_changed(self) -> bool:
        """디스크 파일이 바뀌었으면 메모리에 다시 읽는다."""
        with self._lock:
            if not self.path.exists():
                return False
            try:
                mtime = self.path.stat().st_mtime
            except OSError:
                return False
            prev = getattr(self, "_mtime", None)
            if prev is not None and mtime <= prev:
                return False
            self.load()
            self._mtime = mtime
            return True

    def snapshot(self, *, reload_disk: bool = False) -> dict[str, Any]:
        with self._lock:
            if reload_disk:
                # load()가 잠금을 다시 잡으므로 여기서는 파일만 직접 반영
                try:
                    if self.path.exists():
                        raw = json.loads(self.path.read_text(encoding="utf-8"))
                        merged = self._default()
                        merged.update({k: v for k, v in raw.items() if v is not None})
                        self._data = merged
                        self._ensure_period_unlocked()
                        self._mtime = self.path.stat().st_mtime
                except (json.JSONDecodeError, OSError):
                    pass

            self._ensure_period_unlocked()
            weekly = max(1, int(self._data.get("weekly_included", 1)))
            cursor = max(0, int(self._data.get("cursor_used", 0)))
            grok = max(0, int(self._data.get("grok_used", 0)))
            total = cursor + grok
            cursor_pct = round(100.0 * cursor / weekly, 1)
            grok_pct = round(100.0 * grok / weekly, 1)
            used_pct = round(100.0 * total / weekly, 1)
            cycle = self._cycle_info()
            polled_at = _now_iso()

            return {
                "plan": self._data.get("plan", "Premium"),
                "label": self._data.get("label", "Weekly included usage"),
                "weekly_included": weekly,
                "cursor_used": cursor,
                "grok_used": grok,
                "total_used": total,
                "cursor_pct": cursor_pct,
                "grok_pct": grok_pct,
                "used_pct": min(used_pct, 999.0),
                "updated_at": self._data.get("updated_at"),
                "polled_at": polled_at,
                "source": self._data.get("source", "local"),
                "live_display_message": self._data.get("live_display_message"),
                "live_error": self._data.get("live_error"),
                "live_synced": self._data.get("source") == "cursor-live",
                **cycle,
            }

    def update(
        self,
        *,
        cursor_used: int | None = None,
        grok_used: int | None = None,
        weekly_included: int | None = None,
        plan: str | None = None,
        renews_at: str | None = None,
        period_start: str | None = None,
        cycle_weeks: int | None = None,
        used_pct: float | None = None,
        cursor_share: float | None = None,
        cursor_delta: int = 0,
        grok_delta: int = 0,
        source: str = "api",
    ) -> dict[str, Any]:
        with self._lock:
            if weekly_included is not None:
                self._data["weekly_included"] = max(1, int(weekly_included))
            if plan is not None:
                self._data["plan"] = plan
            if renews_at is not None:
                self._data["renews_at"] = renews_at
            if period_start is not None:
                self._data["period_start"] = period_start
            if cycle_weeks is not None:
                self._data["cycle_weeks"] = max(1, min(12, int(cycle_weeks)))

            # used_pct 직접 지정 시 주간 한도 기준으로 Cursor/Grok 배분
            if used_pct is not None:
                weekly = max(1, int(self._data.get("weekly_included", 1)))
                pct = max(0.0, min(100.0, float(used_pct)))
                total_units = int(round(weekly * pct / 100.0))
                share = float(cursor_share) if cursor_share is not None else 0.8
                share = max(0.0, min(1.0, share))
                # 기존 비율 유지(둘 다 0이 아닐 때)
                cur = int(self._data.get("cursor_used", 0))
                gr = int(self._data.get("grok_used", 0))
                if cursor_share is None and (cur + gr) > 0:
                    share = cur / (cur + gr)
                c_units = int(round(total_units * share))
                g_units = max(0, total_units - c_units)
                self._data["cursor_used"] = c_units
                self._data["grok_used"] = g_units

            if cursor_used is not None:
                self._data["cursor_used"] = max(0, int(cursor_used))
            if grok_used is not None:
                self._data["grok_used"] = max(0, int(grok_used))
            if cursor_delta:
                self._data["cursor_used"] = max(
                    0, int(self._data.get("cursor_used", 0)) + int(cursor_delta)
                )
            if grok_delta:
                self._data["grok_used"] = max(
                    0, int(self._data.get("grok_used", 0)) + int(grok_delta)
                )
            self._data["source"] = source
            # live 메타는 update kwargs에 직접 넣지 않고 apply_live에서 설정
            self._ensure_period_unlocked()
            self._save_unlocked()
            return self.snapshot()

    def apply_live(self, live: dict[str, Any], *, error: str | None = None) -> dict[str, Any]:
        """Cursor Live API 결과를 저장소에 반영."""
        if error:
            with self._lock:
                self._data["live_error"] = error
                self._save_unlocked()
                return self.snapshot(reload_disk=False)
        snap = self.update(
            plan=live.get("plan"),
            renews_at=live.get("renews_at"),
            period_start=live.get("period_start"),
            cycle_weeks=live.get("cycle_weeks"),
            weekly_included=live.get("weekly_included"),
            cursor_used=live.get("cursor_used"),
            grok_used=live.get("grok_used"),
            source="cursor-live",
        )
        with self._lock:
            self._data["live_error"] = None
            self._data["live_display_message"] = live.get("live_display_message")
            self._data["live_total_percent"] = live.get("live_total_percent")
            self._save_unlocked()
        return self.snapshot(reload_disk=False)

    def apply_agent_payload(self, agent: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        keys = (
            "cursor_used",
            "grok_used",
            "weekly_included",
            "tokens_used",
            "token_delta",
            "plan",
            "renews_at",
            "period_start",
            "cycle_weeks",
        )
        if not any(k in payload for k in keys):
            return None

        kwargs: dict[str, Any] = {"source": f"heartbeat:{agent}"}
        for key in ("weekly_included", "cycle_weeks"):
            if key in payload:
                kwargs[key] = int(payload[key])
        for key in ("plan", "renews_at", "period_start"):
            if key in payload:
                kwargs[key] = str(payload[key])

        if "cursor_used" in payload or "grok_used" in payload:
            if "cursor_used" in payload:
                kwargs["cursor_used"] = int(payload["cursor_used"])
            if "grok_used" in payload:
                kwargs["grok_used"] = int(payload["grok_used"])
        elif "tokens_used" in payload:
            used = int(payload["tokens_used"])
            if agent == "grok":
                kwargs["grok_used"] = used
            else:
                kwargs["cursor_used"] = used
        elif "token_delta" in payload:
            delta = int(payload["token_delta"])
            if agent == "grok":
                kwargs["grok_delta"] = delta
            else:
                kwargs["cursor_delta"] = delta

        return self.update(**kwargs)
