"""에이전트 HEARTBEAT 추적. 90초 무응답 시 OFFLINE."""

from __future__ import annotations

import time
from typing import Any

from app.config import HEARTBEAT_TIMEOUT_SEC


class HeartbeatTracker:
    def __init__(self, timeout_sec: float = HEARTBEAT_TIMEOUT_SEC) -> None:
        self.timeout_sec = timeout_sec
        self._last: dict[str, float] = {}

    def beat(self, agent: str) -> None:
        self._last[agent] = time.monotonic()

    def is_online(self, agent: str) -> bool:
        ts = self._last.get(agent)
        if ts is None:
            return False
        return (time.monotonic() - ts) <= self.timeout_sec

    def status_map(self) -> dict[str, bool]:
        return {
            "cursor": self.is_online("cursor"),
            "grok": self.is_online("grok"),
        }

    def detail(self) -> dict[str, Any]:
        now = time.monotonic()
        out: dict[str, Any] = {}
        for agent in ("cursor", "grok"):
            ts = self._last.get(agent)
            out[agent] = {
                "online": self.is_online(agent),
                "last_beat_age_sec": None if ts is None else round(now - ts, 2),
            }
        return out
