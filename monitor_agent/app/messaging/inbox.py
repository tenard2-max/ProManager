"""메시지 수신기: 검증, 멱등, ACK/REJECT."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import SCHEMA_VERSION
from app.history.log import HistoryLog
from app.ini.schemas import SpecValidationError, StatusValidationError
from app.ini.spec_parser import parse_spec_text
from app.ini.status_store import StatusStore
from app.messaging.heartbeat import HeartbeatTracker
from app.models.messages import Envelope, MessageType


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class MessageInbox:
    def __init__(
        self,
        status_store: StatusStore,
        history: HistoryLog,
        heartbeat: HeartbeatTracker,
        command_ack_handler: Any | None = None,
        spec_writer: Any | None = None,
        token_store: Any | None = None,
    ) -> None:
        self.status_store = status_store
        self.history = history
        self.heartbeat = heartbeat
        self.command_ack_handler = command_ack_handler
        self.spec_writer = spec_writer
        self.token_store = token_store
        self._seen: dict[str, dict[str, Any]] = {}

    def handle(self, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            env = Envelope.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            self.history.append(
                "message_schema_error",
                {"error": str(exc), "raw": raw},
            )
            return self._reject(
                raw.get("msg_id", str(uuid.uuid4())),
                reason=f"스키마 검증 실패: {exc}",
                to=raw.get("from", "unknown"),
            )

        if env.schema_version != SCHEMA_VERSION:
            return self._reject(
                env.msg_id,
                reason=f"schema_version 불일치: {env.schema_version}",
                to=env.from_agent,
            )

        # 멱등: 동일 msg_id면 재처리 없이 ACK만
        if env.msg_id in self._seen and env.type != MessageType.ACK:
            prev = self._seen[env.msg_id]
            self.history.append(
                "message_idempotent_ack",
                {"msg_id": env.msg_id, "type": env.type.value},
            )
            return prev["ack"]

        try:
            result = self._dispatch(env)
        except (SpecValidationError, StatusValidationError, ValueError) as exc:
            reject = self._reject(env.msg_id, reason=str(exc), to=env.from_agent)
            self.history.append(
                "message_rejected",
                {"msg_id": env.msg_id, "type": env.type.value, "reason": str(exc)},
            )
            return reject

        ack = self._ack(env, result=result)
        if env.type != MessageType.ACK:
            self._seen[env.msg_id] = {"ack": ack, "result": result}
        self.history.append(
            "message_handled",
            {
                "msg_id": env.msg_id,
                "type": env.type.value,
                "from": env.from_agent,
                "to": env.to,
                "result": result,
            },
        )
        return ack

    def _dispatch(self, env: Envelope) -> dict[str, Any]:
        if env.type == MessageType.HEARTBEAT:
            agent = env.from_agent
            if agent in ("cursor", "grok"):
                self.heartbeat.beat(agent)
            token_snap = None
            if self.token_store and agent in ("cursor", "grok"):
                # payload에 토큰 필드가 있을 때만 갱신 (매 심박 가산 금지)
                token_snap = self.token_store.apply_agent_payload(
                    agent, env.payload or {}
                )
            return {"ok": True, "agent": agent, "tokens": token_snap}

        if env.type == MessageType.SPEC_RESET:
            spec_text = env.payload.get("spec_ini", "")
            if not spec_text:
                raise ValueError("payload.spec_ini 필수")
            spec = parse_spec_text(spec_text, strict=True)
            if spec.errors:
                raise SpecValidationError("; ".join(spec.errors))
            if self.spec_writer:
                self.spec_writer(spec_text)
            doc, diff = self.status_store.apply_spec_reset(
                spec, updated_by=env.from_agent
            )
            self.history.append(
                "spec_reset",
                {"diff": diff, "state_version": doc.meta.get("state_version")},
            )
            return {"diff": diff, "total_tasks": len(doc.items)}

        if env.type == MessageType.STATUS_UPDATE:
            req_id = env.payload.get("req_id")
            if not req_id:
                raise ValueError("payload.req_id 필수")
            doc = self.status_store.update_from_cursor(
                req_id,
                status=env.payload.get("status"),
                progress=env.payload.get("progress"),
                dev_note=env.payload.get("dev_note"),
                expected_version=env.payload.get("expected_version"),
                updated_by=env.from_agent,
            )
            return {
                "req_id": req_id,
                "progress": doc.items[req_id].progress,
                "state_version": doc.meta.get("state_version"),
            }

        if env.type == MessageType.QA_RESULT:
            req_id = env.payload.get("req_id")
            if not req_id:
                raise ValueError("payload.req_id 필수")
            doc = self.status_store.apply_qa_result(
                req_id,
                qa_status=env.payload.get("qa_status", "PENDING"),
                qa_score=int(env.payload.get("qa_score", 0)),
                qa_diff_note=env.payload.get("qa_diff_note", ""),
                expected_version=env.payload.get("expected_version"),
                updated_by=env.from_agent,
            )
            item = doc.items[req_id]
            return {
                "req_id": req_id,
                "qa_status": item.qa_status,
                "progress": item.progress,
                "qa_rework_count": item.qa_rework_count,
                "state_version": doc.meta.get("state_version"),
            }

        if env.type == MessageType.ACK:
            if self.command_ack_handler:
                self.command_ack_handler(env)
            return {"ok": True}

        raise ValueError(f"수신 불가 유형: {env.type}")

    def _ack(self, env: Envelope, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "msg_id": str(uuid.uuid4()),
            "type": MessageType.ACK.value,
            "from": "agent",
            "to": env.from_agent,
            "ts": _now_iso(),
            "schema_version": SCHEMA_VERSION,
            "payload": {
                "ack_for": env.msg_id,
                "status": "ok",
                "result": result,
            },
        }

    def _reject(self, msg_id: str, reason: str, to: str) -> dict[str, Any]:
        return {
            "msg_id": str(uuid.uuid4()),
            "type": MessageType.REJECT.value,
            "from": "agent",
            "to": to,
            "ts": _now_iso(),
            "schema_version": SCHEMA_VERSION,
            "payload": {"ack_for": msg_id, "status": "reject", "reason": reason},
        }
