"""DoD 통합: FastAPI TestClient."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "snapshots").mkdir()
    (data / "history").mkdir()

    import app.config as cfg

    monkeypatch.setattr(cfg, "DATA_DIR", data)
    monkeypatch.setattr(cfg, "SPEC_PATH", data / "spec.ini")
    monkeypatch.setattr(cfg, "STATUS_PATH", data / "project_status.ini")
    monkeypatch.setattr(cfg, "SNAPSHOT_DIR", data / "snapshots")
    monkeypatch.setattr(cfg, "HISTORY_DIR", data / "history")
    monkeypatch.setattr(cfg, "HISTORY_LOG_PATH", data / "history" / "events.jsonl")

    # 모듈 싱글톤 재구성
    import importlib
    import app.main as main

    importlib.reload(main)

    with TestClient(main.app) as c:
        yield c


SPEC_TEXT = """[META]
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


def test_spec_reset_shows_in_state(client: TestClient):
    msg = {
        "msg_id": str(uuid.uuid4()),
        "type": "SPEC_RESET",
        "from": "cursor",
        "to": "agent",
        "ts": "2026-11-13T10:00:00+09:00",
        "schema_version": 1,
        "payload": {"spec_ini": SPEC_TEXT},
    }
    r = client.post("/api/messages", json=msg)
    assert r.status_code == 200
    assert r.json()["type"] == "ACK"
    state = client.get("/api/state").json()
    assert len(state["items"]) == 1
    assert state["items"][0]["req_id"] == "REQ_001"


def test_cursor_progress_61_rejected(client: TestClient):
    client.post(
        "/api/messages",
        json={
            "msg_id": str(uuid.uuid4()),
            "type": "SPEC_RESET",
            "from": "cursor",
            "to": "agent",
            "ts": "2026-11-13T10:00:00+09:00",
            "schema_version": 1,
            "payload": {"spec_ini": SPEC_TEXT},
        },
    )
    r = client.post(
        "/api/messages",
        json={
            "msg_id": str(uuid.uuid4()),
            "type": "STATUS_UPDATE",
            "from": "cursor",
            "to": "agent",
            "ts": "2026-11-13T10:00:00+09:00",
            "schema_version": 1,
            "payload": {"req_id": "REQ_001", "progress": 61},
        },
    )
    assert r.json()["type"] == "REJECT"
