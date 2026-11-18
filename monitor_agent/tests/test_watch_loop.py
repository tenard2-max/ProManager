"""Phase 3: 감시 루프 해시 감지."""

from __future__ import annotations

from pathlib import Path

from app.history.log import HistoryLog
from app.ini.spec_parser import parse_spec_text
from app.ini.status_store import StatusStore
from app.watch.loop import WatchLoop, file_sha256


SPEC = """
[META]
project_name = Demo
spec_version = 1
submitted_by = cursor
submitted_at = 2026-11-13T10:00:00+09:00

[REQ_001]
title = Sample
category = Core
priority = HIGH
spec_ref = 1.1
acceptance_criteria = must pass
target_files = a.py
"""


def test_watch_detects_status_change(tmp_path: Path):
    spec_path = tmp_path / "spec.ini"
    status_path = tmp_path / "project_status.ini"
    snap = tmp_path / "snapshots"
    spec_path.write_text(SPEC, encoding="utf-8")

    store = StatusStore(status_path)
    store.apply_spec_reset(parse_spec_text(SPEC))
    history = HistoryLog(tmp_path / "events.jsonl")

    loop = WatchLoop(
        store,
        history,
        spec_path=spec_path,
        status_path=status_path,
        snapshot_dir=snap,
    )
    r1 = loop.tick()
    assert r1["changed"] is True
    h1 = file_sha256(status_path)

    r2 = loop.tick()
    assert r2["changed"] is False

    # 외부 수정 시뮬레이션
    text = status_path.read_text(encoding="utf-8")
    status_path.write_text(text + "\n; touch\n", encoding="utf-8")
    r3 = loop.tick()
    assert r3["changed"] is True
    assert file_sha256(status_path) != h1
    assert (snap / "project_status.ini").exists()
