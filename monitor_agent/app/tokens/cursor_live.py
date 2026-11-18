"""Cursor IDE 로컬 인증 → Dashboard API로 주 사용량 자동 수집."""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CONNECT_HEADERS_EXTRA = {
    "Content-Type": "application/json",
    "Connect-Protocol-Version": "1",
}
PERIOD_URL = (
    "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
)
SAND_URL = (
    "https://api2.cursor.sh/aiserver.v1.DashboardService/GetSandUsageStatus"
)
PLAN_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetPlanInfo"
TOKEN_URL = "https://api2.cursor.sh/oauth/token"


def _default_state_db() -> Path:
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Cursor"
        / "User"
        / "globalStorage"
        / "state.vscdb"
    )


def _ms_to_iso(ms: str | int | float | None) -> str | None:
    if ms is None or ms == "":
        return None
    try:
        value = float(ms)
        if value > 1e12:  # already ms
            value = value / 1000.0
        dt = datetime.fromtimestamp(value, tz=timezone.utc).astimezone()
        return dt.isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


class CursorLiveUsageClient:
    """state.vscdb의 accessToken으로 Cursor 사용량을 조회한다."""

    def __init__(self, state_db: Path | None = None) -> None:
        self.state_db = Path(state_db) if state_db else _default_state_db()
        self._access: str | None = None
        self._refresh: str | None = None
        self._last_error: str | None = None
        self._last_ok_at: float | None = None
        self._last_raw: dict[str, Any] = {}

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _read_auth(self) -> tuple[str | None, str | None]:
        if not self.state_db.exists():
            self._last_error = f"Cursor state DB 없음: {self.state_db}"
            return None, None
        try:
            con = sqlite3.connect(f"file:{self.state_db}?mode=ro", uri=True)
            cur = con.cursor()

            def _get(key: str) -> str | None:
                row = cur.execute(
                    "SELECT value FROM ItemTable WHERE key=?", (key,)
                ).fetchone()
                if not row or row[0] is None:
                    return None
                val = row[0]
                if isinstance(val, bytes):
                    val = val.decode("utf-8", errors="ignore")
                return str(val).strip().strip('"') or None

            access = _get("cursorAuth/accessToken")
            refresh = _get("cursorAuth/refreshToken")
            con.close()
            if not access:
                self._last_error = "cursorAuth/accessToken 없음 (Cursor 로그인 필요)"
            return access, refresh
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"auth 읽기 실패: {exc}"
            return None, None

    def _refresh_access_token(self) -> bool:
        if not self._refresh:
            return False
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.post(
                    TOKEN_URL,
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh,
                    },
                )
            if r.status_code != 200:
                self._last_error = f"토큰 갱신 실패 HTTP {r.status_code}"
                return False
            data = r.json()
            access = data.get("access_token")
            refresh = data.get("refresh_token")
            if not access:
                self._last_error = "토큰 갱신 응답에 access_token 없음"
                return False
            self._access = access
            if refresh:
                self._refresh = refresh
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"토큰 갱신 예외: {exc}"
            return False

    def _post_connect(self, url: str) -> dict[str, Any] | None:
        if not self._access:
            return None
        headers = {"Authorization": f"Bearer {self._access}", **CONNECT_HEADERS_EXTRA}
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.post(url, headers=headers, content=b"{}")
                if r.status_code in (401, 403):
                    if self._refresh_access_token():
                        headers["Authorization"] = f"Bearer {self._access}"
                        r = client.post(url, headers=headers, content=b"{}")
                if r.status_code != 200:
                    self._last_error = f"{url.rsplit('/', 1)[-1]} HTTP {r.status_code}"
                    return None
                return r.json()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"API 호출 실패: {exc}"
            return None

    def fetch(self) -> dict[str, Any] | None:
        """성공 시 TokenUsageStore.update에 넣을 필드 dict 반환."""
        access, refresh = self._read_auth()
        self._access = access
        self._refresh = refresh
        if not access:
            return None

        period = self._post_connect(PERIOD_URL)
        if not period:
            return None
        sand = self._post_connect(SAND_URL) or {}
        plan = self._post_connect(PLAN_URL) or {}

        plan_usage = period.get("planUsage") or {}
        total_pct = float(
            plan_usage.get("totalPercentUsed")
            or plan_usage.get("autoPercentUsed")
            or 0.0
        )
        auto_pct = float(plan_usage.get("autoPercentUsed") or total_pct)
        api_pct = float(plan_usage.get("apiPercentUsed") or 0.0)
        # 통합 요금제: Cursor/Grok 공용. 분리값이 없으면 Auto=Cursor, API=기타
        cursor_pct = auto_pct
        grok_pct = api_pct
        if grok_pct <= 0 and sand.get("isUnified") is False:
            grok_pct = float(sand.get("usagePercent") or 0.0)
        # 합이 total을 넘지 않게 보정
        if cursor_pct + grok_pct <= 0:
            cursor_pct = total_pct
            grok_pct = 0.0
        elif abs((cursor_pct + grok_pct) - total_pct) > 0.5 and api_pct <= 0:
            # 공용 풀: 막대는 합계만 쓰고 Cursor에 전부 배정
            cursor_pct = total_pct
            grok_pct = 0.0

        renews = _ms_to_iso(period.get("billingCycleEnd"))
        start = _ms_to_iso(period.get("billingCycleStart"))
        if not renews and sand.get("nextResetTimestampUtc"):
            renews = str(sand["nextResetTimestampUtc"]).replace("Z", "+00:00")
            try:
                renews = (
                    datetime.fromisoformat(renews).astimezone().isoformat(timespec="seconds")
                )
            except ValueError:
                pass
        if not start and sand.get("currentPeriodStart"):
            start = str(sand["currentPeriodStart"]).replace("Z", "+00:00")
            try:
                start = (
                    datetime.fromisoformat(start).astimezone().isoformat(timespec="seconds")
                )
            except ValueError:
                pass

        plan_info = (plan.get("planInfo") or {}) if isinstance(plan, dict) else {}
        plan_name = (
            sand.get("cursorPlanName")
            or plan_info.get("planName")
            or "Premium"
        )

        # 주간 구간이면 cycle_weeks=1, 아니면 4주 구독 표시용
        cycle_weeks = 1
        if start and renews:
            try:
                s = datetime.fromisoformat(start)
                e = datetime.fromisoformat(renews)
                days = max(1, (e - s).total_seconds() / 86400.0)
                cycle_weeks = 1 if days <= 8 else max(1, min(4, round(days / 7)))
            except ValueError:
                cycle_weeks = 1

        weekly = 1_000_000
        cursor_used = int(round(weekly * cursor_pct / 100.0))
        grok_used = int(round(weekly * grok_pct / 100.0))

        self._last_error = None
        self._last_ok_at = time.time()
        self._last_raw = {
            "displayMessage": period.get("displayMessage"),
            "totalPercentUsed": total_pct,
            "isUnified": sand.get("isUnified"),
        }
        return {
            "plan": str(plan_name),
            "label": "Weekly included usage",
            "renews_at": renews,
            "period_start": start,
            "cycle_weeks": cycle_weeks,
            "weekly_included": weekly,
            "cursor_used": cursor_used,
            "grok_used": grok_used,
            "source": "cursor-live",
            "live_display_message": period.get("displayMessage"),
            "live_total_percent": round(total_pct, 2),
        }
