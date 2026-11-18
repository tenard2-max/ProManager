"""Phase 2: 상태 저장소 및 진행률 권한."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ini.schemas import StatusValidationError
from app.ini.spec_parser import parse_spec_text
from app.ini.status_store import StatusStore, compute_qa_progress


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


def test_compute_qa_progress():
    assert compute_qa_progress(90) == 98
    assert compute_qa_progress(0) == 80
    assert compute_qa_progress(100) == 100


def test_spec_reset_and_cursor_progress_cap(tmp_path: Path):
    store = StatusStore(tmp_path / "project_status.ini")
    spec = parse_spec_text(SPEC)
    doc, diff = store.apply_spec_reset(spec)
    assert "REQ_001" in doc.items
    assert "REQ_001" in diff["added"]

    store.update_from_cursor("REQ_001", status="IN_REVIEW", progress=60, dev_note="done")
    assert store.document.items["REQ_001"].progress == 60

    with pytest.raises(StatusValidationError):
        store.update_from_cursor("REQ_001", progress=61)


def test_qa_rework_increments_count(tmp_path: Path):
    store = StatusStore(tmp_path / "project_status.ini")
    store.apply_spec_reset(parse_spec_text(SPEC))
    store.update_from_cursor("REQ_001", status="IN_REVIEW", progress=60)
    store.apply_qa_result(
        "REQ_001", qa_status="FAILED_REWORK", qa_score=40, qa_diff_note="bug"
    )
    item = store.document.items["REQ_001"]
    assert item.status == "REWORK_REQUESTED"
    assert item.qa_rework_count == 1
    assert item.progress == 60


def test_qa_passed_sets_progress_80_plus(tmp_path: Path):
    store = StatusStore(tmp_path / "project_status.ini")
    store.apply_spec_reset(parse_spec_text(SPEC))
    store.update_from_cursor("REQ_001", status="IN_REVIEW", progress=60)
    store.apply_qa_result("REQ_001", qa_status="PASSED", qa_score=90)
    item = store.document.items["REQ_001"]
    assert item.progress == 98
    assert item.qa_status == "PASSED"


def test_state_version_conflict(tmp_path: Path):
    store = StatusStore(tmp_path / "project_status.ini")
    store.apply_spec_reset(parse_spec_text(SPEC))
    ver = int(store.document.meta["state_version"])
    with pytest.raises(StatusValidationError):
        store.update_from_cursor(
            "REQ_001", progress=10, expected_version=ver - 1
        )


def test_final_approve_requires_passed(tmp_path: Path):
    store = StatusStore(tmp_path / "project_status.ini")
    store.apply_spec_reset(parse_spec_text(SPEC))
    with pytest.raises(StatusValidationError):
        store.apply_user_command_state(["REQ_001"], "final_approve")
