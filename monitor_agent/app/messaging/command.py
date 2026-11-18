"""발주자 명령 전달 및 ACK 추적."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import ACK_MAX_RETRIES, ACK_TIMEOUT_SEC, SCHEMA_VERSION
from app.history.log import HistoryLog
from app.ini.status_store import StatusStore
from app.models.messages import CommandRequest, MessageType


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class TrackedCommand:
    msg_id: str
    target: str
    command_type: str
    req_ids: list[str]
    note: str
    status: str = "pending"  # pending | received | completed | failed
    created_at: float = field(default_factory=time.monotonic)
    created_at_iso: str = field(default_factory=_now_iso)
    retries: int = 0
    last_sent_at: float = field(default_factory=time.monotonic)
    ack_latency_ms: float | None = None
    envelope: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "target": self.target,
            "command_type": self.command_type,
            "req_ids": self.req_ids,
            "note": self.note,
            "status": self.status,
            "created_at": self.created_at_iso,
            "retries": self.retries,
            "ack_latency_ms": self.ack_latency_ms,
        }


class CommandDispatcher:
    def __init__(
        self,
        status_store: StatusStore,
        history: HistoryLog,
        *,
        ack_timeout: float = ACK_TIMEOUT_SEC,
        max_retries: int = ACK_MAX_RETRIES,
    ) -> None:
        self.status_store = status_store
        self.history = history
        self.ack_timeout = ack_timeout
        self.max_retries = max_retries
        self._outbox: dict[str, list[TrackedCommand]] = {
            "cursor": [],
            "grok": [],
        }
        self._by_id: dict[str, TrackedCommand] = {}

    def submit(self, req: CommandRequest) -> TrackedCommand:
        if req.target not in ("cursor", "grok"):
            raise ValueError("target은 cursor 또는 grok")

        # 상태 전환은 관제 에이전트가 즉시 적용
        if req.command_type in (
            "extra_verify",
            "rework",
            "qa_reeval",
            "final_approve",
        ):
            # final_approve / extra_verify 등은 상태 저장소에 반영
            # qa_reeval은 grok 대상, rework/extra_verify는 상태+대상 에이전트
            apply_types = ("extra_verify", "rework", "final_approve", "qa_reeval")
            if req.command_type in apply_types:
                self.status_store.apply_user_command_state(
                    req.req_ids, req.command_type, note=req.note
                )

        msg_id = str(uuid.uuid4())
        envelope = {
            "msg_id": msg_id,
            "type": MessageType.COMMAND.value,
            "from": "user",
            "to": req.target,
            "ts": _now_iso(),
            "schema_version": SCHEMA_VERSION,
            "payload": {
                "command_type": req.command_type,
                "req_ids": req.req_ids,
                "note": req.note,
            },
        }
        tracked = TrackedCommand(
            msg_id=msg_id,
            target=req.target,
            command_type=req.command_type,
            req_ids=list(req.req_ids),
            note=req.note,
            envelope=envelope,
        )
        self._outbox[req.target].append(tracked)
        self._by_id[msg_id] = tracked
        self.history.append(
            "command_submitted",
            tracked.to_dict(),
        )
        return tracked

    def poll_outbox(self, agent: str) -> list[dict[str, Any]]:
        self._expire_and_retry()
        items = [
            t
            for t in self._outbox.get(agent, [])
            if t.status in ("pending", "received")
        ]
        result = []
        for t in items:
            if t.status == "pending":
                t.status = "received"
            result.append(t.envelope)
        return result

    def handle_ack(self, env: Any) -> None:
        ack_for = env.payload.get("ack_for")
        if not ack_for or ack_for not in self._by_id:
            return
        tracked = self._by_id[ack_for]
        tracked.status = "completed"
        tracked.ack_latency_ms = round(
            (time.monotonic() - tracked.created_at) * 1000, 2
        )
        self.history.append(
            "command_ack",
            {
                "msg_id": tracked.msg_id,
                "ack_latency_ms": tracked.ack_latency_ms,
            },
        )

    def _expire_and_retry(self) -> None:
        now = time.monotonic()
        for agent, queue in self._outbox.items():
            for t in queue:
                if t.status == "completed" or t.status == "failed":
                    continue
                if now - t.last_sent_at < self.ack_timeout:
                    continue
                if t.retries >= self.max_retries:
                    t.status = "failed"
                    self.history.append(
                        "command_failed",
                        {"msg_id": t.msg_id, "retries": t.retries},
                    )
                    continue
                t.retries += 1
                t.last_sent_at = now
                t.status = "pending"
                self.history.append(
                    "command_retry",
                    {"msg_id": t.msg_id, "retries": t.retries},
                )

    def list_commands(self, limit: int = 50) -> list[dict[str, Any]]:
        self._expire_and_retry()
        items = sorted(
            self._by_id.values(), key=lambda x: x.created_at, reverse=True
        )
        return [i.to_dict() for i in items[:limit]]
