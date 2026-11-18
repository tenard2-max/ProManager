"""메시지 봉투 스키마."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    SPEC_RESET = "SPEC_RESET"
    STATUS_UPDATE = "STATUS_UPDATE"
    QA_RESULT = "QA_RESULT"
    COMMAND = "COMMAND"
    ACK = "ACK"
    HEARTBEAT = "HEARTBEAT"
    REJECT = "REJECT"


class Envelope(BaseModel):
    msg_id: str
    type: MessageType
    from_agent: str = Field(alias="from")
    to: str
    ts: str
    schema_version: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class CommandRequest(BaseModel):
    target: str  # cursor | grok
    req_ids: list[str]
    command_type: str  # extra_verify | rework | qa_reeval | final_approve
    note: str = ""
