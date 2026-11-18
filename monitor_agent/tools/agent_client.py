"""Cursor/Grok용 간단 HTTP 클라이언트 예제 (로컬 전용)."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:18765"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def envelope(typ: str, frm: str, payload: dict, to: str = "agent") -> dict:
    return {
        "msg_id": str(uuid.uuid4()),
        "type": typ,
        "from": frm,
        "to": to,
        "ts": _now(),
        "schema_version": 1,
        "payload": payload,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["heartbeat", "spec_reset", "status", "qa", "poll"])
    p.add_argument("--agent", default="cursor", choices=["cursor", "grok"])
    p.add_argument("--req", default="REQ_001")
    p.add_argument("--progress", type=int, default=60)
    p.add_argument("--qa-status", default="PASSED")
    p.add_argument("--qa-score", type=int, default=90)
    p.add_argument("--spec", type=Path, default=None)
    args = p.parse_args()

    with httpx.Client(base_url=BASE, timeout=10.0) as client:
        if args.action == "heartbeat":
            body = envelope("HEARTBEAT", args.agent, {})
            print(client.post("/api/messages", json=body).json())
        elif args.action == "spec_reset":
            path = args.spec or Path(__file__).resolve().parent.parent / "data" / "spec.ini"
            body = envelope("SPEC_RESET", "cursor", {"spec_ini": path.read_text(encoding="utf-8")})
            print(client.post("/api/messages", json=body).json())
        elif args.action == "status":
            body = envelope(
                "STATUS_UPDATE",
                "cursor",
                {
                    "req_id": args.req,
                    "progress": args.progress,
                    "status": "IN_REVIEW",
                    "dev_note": "client update",
                },
            )
            print(client.post("/api/messages", json=body).json())
        elif args.action == "qa":
            body = envelope(
                "QA_RESULT",
                "grok",
                {
                    "req_id": args.req,
                    "qa_status": args.qa_status,
                    "qa_score": args.qa_score,
                    "qa_diff_note": "",
                },
            )
            print(client.post("/api/messages", json=body).json())
        elif args.action == "poll":
            print(client.get("/api/messages/outbox", params={"agent": args.agent}).json())


if __name__ == "__main__":
    main()
