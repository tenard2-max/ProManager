"""Phase 7: 지표 산출과 이력 재계산 일치."""

from __future__ import annotations

from pathlib import Path

from app.history.log import HistoryLog
from app.ini.spec_parser import parse_spec_text
from app.ini.status_store import StatusStore
from app.metrics.calculator import MetricsCalculator


SPEC = """
[META]
project_name = Demo
spec_version = 1
submitted_by = cursor
submitted_at = 2026-11-13T10:00:00+09:00

[REQ_001]
title = A
category = Core
priority = HIGH
spec_ref = 1
acceptance_criteria = x
target_files = a.py

[REQ_002]
title = B
category = Core
priority = LOW
spec_ref = 2
acceptance_criteria = y
target_files = b.py
"""


def test_metrics_recalc_matches(tmp_path: Path):
    store = StatusStore(tmp_path / "project_status.ini")
    history = HistoryLog(tmp_path / "events.jsonl")
    store.apply_spec_reset(parse_spec_text(SPEC))
    store.update_from_cursor("REQ_001", progress=60, status="IN_REVIEW")
    store.apply_qa_result("REQ_001", qa_status="PASSED", qa_score=90)
    store.apply_user_command_state(["REQ_001"], "final_approve")

    history.append(
        "message_handled",
        {
            "msg_id": "q1",
            "type": "QA_RESULT",
            "from": "grok",
            "to": "agent",
            "result": {"req_id": "REQ_001", "qa_status": "PASSED", "progress": 98},
        },
    )
    history.append(
        "command_ack",
        {"msg_id": "c1", "ack_latency_ms": 12.5},
    )

    calc = MetricsCalculator(store, history)
    live = calc.calculate()
    recalc = calc.recalculate_from_history()

    for key in (
        "first_pass_rate",
        "avg_rework_count",
        "requirement_fulfillment_rate",
        "avg_command_ack_ms",
    ):
        assert live[key] == recalc[key]

    assert live["requirement_fulfillment_rate"] == 0.5
    assert live["avg_command_ack_ms"] == 12.5
