"""Cursor live 응답 → 저장 필드 변환(네트워크 없이 epoch 파싱만)."""

from __future__ import annotations

from app.tokens.cursor_live import _ms_to_iso


def test_ms_to_iso_weekly_window():
    start = _ms_to_iso("1794789646967")
    end = _ms_to_iso("1795394446967")
    assert start is not None and start.startswith("2026-11-16")
    assert end is not None and end.startswith("2026-11-23")
