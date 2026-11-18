"""Phase 4–5: 메시지 멱등·ACK·진행률 거부·명령."""

from __future__ import annotations

from pathlib import Path

from app.history.log import HistoryLog
from app.ini.spec_parser import parse_spec_text
from app.ini.status_store import StatusStore
from app.messaging.command import CommandDispatcher
from app.messaging.heartbeat import HeartbeatTracker
from app.messaging.inbox import MessageInbox
from app.models.messages import CommandRequest


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


def _inbox(tmp_path: Path) -> tuple[MessageInbox, StatusStore, CommandDispatcher]:
    store = StatusStore(tmp_path / "project_status.ini")
    store.apply_spec_reset(parse_spec_text(SPEC))
    history = HistoryLog(tmp_path / "events.jsonl")
    hb = HeartbeatTracker(timeout_sec=90)
    cmds = CommandDispatcher(store, history)
    inbox = MessageInbox(store, history, hb, command_ack_handler=cmds.handle_ack)
    return inbox, store, cmds


def _env(msg_id: str, typ: str, payload: dict, frm: str = "cursor") -> dict:
    return {
        "msg_id": msg_id,
        "type": typ,
        "from": frm,
        "to": "agent",
        "ts": "2026-11-13T10:00:00+09:00",
        "schema_version": 1,
        "payload": payload,
    }


def test_progress_over_60_rejected(tmp_path: Path):
    inbox, store, _ = _inbox(tmp_path)
    resp = inbox.handle(
        _env("m1", "STATUS_UPDATE", {"req_id": "REQ_001", "progress": 61})
    )
    assert resp["type"] == "REJECT"
    assert store.document.items["REQ_001"].progress == 0


def test_idempotent_msg_id(tmp_path: Path):
    inbox, store, _ = _inbox(tmp_path)
    msg = _env(
        "same-id",
        "STATUS_UPDATE",
        {"req_id": "REQ_001", "progress": 40, "status": "IN_PROGRESS"},
    )
    r1 = inbox.handle(msg)
    assert r1["type"] == "ACK"
    store.document.items["REQ_001"].progress = 40
    r2 = inbox.handle(msg)
    assert r2["type"] == "ACK"
    assert r2["payload"]["ack_for"] == "same-id"
    # 두 번째 처리로 progress가 변하지 않음(이미 40)
    assert store.document.items["REQ_001"].progress == 40


def test_qa_result_and_rework_count(tmp_path: Path):
    inbox, store, _ = _inbox(tmp_path)
    inbox.handle(
        _env("u1", "STATUS_UPDATE", {"req_id": "REQ_001", "progress": 60, "status": "IN_REVIEW"})
    )
    r = inbox.handle(
        _env(
            "q1",
            "QA_RESULT",
            {"req_id": "REQ_001", "qa_status": "FAILED_REWORK", "qa_score": 30},
            frm="grok",
        )
    )
    assert r["type"] == "ACK"
    assert store.document.items["REQ_001"].qa_rework_count == 1


def test_heartbeat_online(tmp_path: Path):
    inbox, _, _ = _inbox(tmp_path)
    hb = inbox.heartbeat
    assert hb.is_online("cursor") is False
    inbox.handle(_env("h1", "HEARTBEAT", {}, frm="cursor"))
    assert hb.is_online("cursor") is True


def test_command_ack_tracking(tmp_path: Path):
    inbox, store, cmds = _inbox(tmp_path)
    store.update_from_cursor("REQ_001", progress=60, status="IN_REVIEW")
    store.apply_qa_result("REQ_001", qa_status="PASSED", qa_score=90)
    tracked = cmds.submit(
        CommandRequest(
            target="cursor",
            req_ids=["REQ_001"],
            command_type="final_approve",
            note="",
        )
    )
    assert store.document.items["REQ_001"].status == "VERIFIED"
    out = cmds.poll_outbox("cursor")
    assert out and out[0]["msg_id"] == tracked.msg_id
    inbox.handle(
        {
            "msg_id": "ack1",
            "type": "ACK",
            "from": "cursor",
            "to": "agent",
            "ts": "2026-11-13T10:01:00+09:00",
            "schema_version": 1,
            "payload": {"ack_for": tracked.msg_id},
        }
    )
    assert cmds._by_id[tracked.msg_id].status == "completed"
