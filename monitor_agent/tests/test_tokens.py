"""토큰(주 사용량) 저장소."""

from __future__ import annotations

from pathlib import Path

from app.tokens.usage import TokenUsageStore


def test_snapshot_percentages(tmp_path: Path):
    store = TokenUsageStore(tmp_path / "token_usage.json")
    snap = store.update(
        weekly_included=1_000_000,
        cursor_used=640_000,
        grok_used=190_000,
        renews_at="2026-11-19T00:00:00+09:00",
        period_start="2026-10-22T00:00:00+09:00",
        cycle_weeks=4,
        plan="Premium",
    )
    assert snap["used_pct"] == 83.0
    assert snap["cursor_pct"] == 64.0
    assert snap["grok_pct"] == 19.0
    assert "2026-11-19" in snap["renews_display"]
    assert snap["cycle_weeks"] == 4
    assert 1 <= snap["current_week"] <= 4
    assert 0 <= snap["remain_pct"] <= 100
    assert len(snap["weeks"]) == 4


def test_heartbeat_payload_apply(tmp_path: Path):
    store = TokenUsageStore(tmp_path / "token_usage.json")
    store.update(cursor_used=100, grok_used=50, weekly_included=1000)
    snap = store.apply_agent_payload("cursor", {"token_delta": 50})
    assert snap is not None
    assert snap["cursor_used"] == 150
    assert store.apply_agent_payload("cursor", {"ping": True}) is None
