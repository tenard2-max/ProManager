"""상태 INI(project_status.ini) 저장소 및 진행률 권한 규칙."""

from __future__ import annotations

import configparser
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config as app_config
from app.config import CURSOR_PROGRESS_MAX, QA_PROGRESS_MIN
from app.ini.schemas import (
    QA_STATUS_VALUES,
    STATUS_VALUES,
    StatusValidationError,
)
from app.ini.spec_parser import SpecDocument


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def compute_qa_progress(qa_score: int) -> int:
    """ASSUMPTION-1: progress = 80 + round(qa_score * 0.2)."""
    score = max(0, min(100, int(qa_score)))
    return QA_PROGRESS_MIN + round(score * 0.2)


@dataclass
class StatusItem:
    req_id: str
    title: str
    category: str
    status: str = "TODO"
    progress: int = 0
    qa_status: str = "PENDING"
    qa_score: int = 0
    qa_rework_count: int = 0
    dev_note: str = ""
    qa_diff_note: str = ""
    last_updated_by: str = "agent"
    last_updated_at: str = field(default_factory=_now_iso)
    priority: str = "MEDIUM"
    spec_ref: str = ""
    acceptance_criteria: str = ""
    target_files: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "req_id": self.req_id,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "progress": self.progress,
            "qa_status": self.qa_status,
            "qa_score": self.qa_score,
            "qa_rework_count": self.qa_rework_count,
            "dev_note": self.dev_note,
            "qa_diff_note": self.qa_diff_note,
            "last_updated_by": self.last_updated_by,
            "last_updated_at": self.last_updated_at,
            "priority": self.priority,
            "spec_ref": self.spec_ref,
            "acceptance_criteria": self.acceptance_criteria,
            "target_files": self.target_files,
        }


@dataclass
class StatusDocument:
    meta: dict[str, Any]
    items: dict[str, StatusItem] = field(default_factory=dict)

    def overall_progress(self) -> float:
        if not self.items:
            return 0.0
        return round(
            sum(i.progress for i in self.items.values()) / len(self.items), 2
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": dict(self.meta),
            "items": {k: v.to_dict() for k, v in self.items.items()},
        }


class StatusStore:
    """상태 INI 단독 쓰기 경로. state_version 낙관적 잠금."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else Path(app_config.STATUS_PATH)
        self._lock = threading.RLock()
        self._doc: StatusDocument | None = None

    @property
    def document(self) -> StatusDocument | None:
        return self._doc

    def load(self) -> StatusDocument:
        with self._lock:
            if not self.path.exists():
                self._doc = StatusDocument(
                    meta={
                        "project_name": "",
                        "total_tasks": 0,
                        "overall_progress": 0,
                        "state_version": 0,
                        "last_updated_by": "agent",
                        "last_updated_at": _now_iso(),
                    }
                )
                return self._doc
            text = self.path.read_text(encoding="utf-8-sig")
            self._doc = self._parse(text)
            return self._doc

    def _parse(self, text: str) -> StatusDocument:
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read_string(text)
        if "META" not in parser:
            raise StatusValidationError("META 섹션이 없습니다.", section="META")

        meta_sec = parser["META"]
        meta = {
            "project_name": meta_sec.get("project_name", ""),
            "total_tasks": int(meta_sec.get("total_tasks", "0") or 0),
            "overall_progress": float(meta_sec.get("overall_progress", "0") or 0),
            "state_version": int(meta_sec.get("state_version", "0") or 0),
            "last_updated_by": meta_sec.get("last_updated_by", "agent"),
            "last_updated_at": meta_sec.get("last_updated_at", _now_iso()),
        }
        items: dict[str, StatusItem] = {}
        for name in parser.sections():
            if name == "META" or not name.startswith("REQ_"):
                continue
            sec = parser[name]
            status = sec.get("status", "TODO").strip()
            qa_status = sec.get("qa_status", "PENDING").strip()
            if status not in STATUS_VALUES:
                raise StatusValidationError(
                    f"잘못된 status: {status}", section=name
                )
            if qa_status not in QA_STATUS_VALUES:
                raise StatusValidationError(
                    f"잘못된 qa_status: {qa_status}", section=name
                )
            progress = int(sec.get("progress", "0") or 0)
            if 61 <= progress <= 79:
                raise StatusValidationError(
                    f"progress 61~79는 저장 불가: {progress}", section=name
                )
            items[name] = StatusItem(
                req_id=name,
                title=sec.get("title", ""),
                category=sec.get("category", ""),
                status=status,
                progress=progress,
                qa_status=qa_status,
                qa_score=int(sec.get("qa_score", "0") or 0),
                qa_rework_count=int(sec.get("qa_rework_count", "0") or 0),
                dev_note=sec.get("dev_note", ""),
                qa_diff_note=sec.get("qa_diff_note", ""),
                last_updated_by=sec.get("last_updated_by", "agent"),
                last_updated_at=sec.get("last_updated_at", _now_iso()),
            )
        return StatusDocument(meta=meta, items=items)

    def save(self, doc: StatusDocument, updated_by: str = "agent") -> StatusDocument:
        with self._lock:
            doc.meta["total_tasks"] = len(doc.items)
            doc.meta["overall_progress"] = doc.overall_progress()
            doc.meta["state_version"] = int(doc.meta.get("state_version", 0)) + 1
            doc.meta["last_updated_by"] = updated_by
            doc.meta["last_updated_at"] = _now_iso()
            self._write(doc)
            self._doc = doc
            return doc

    def _write(self, doc: StatusDocument) -> None:
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser["META"] = {
            "project_name": str(doc.meta.get("project_name", "")),
            "total_tasks": str(doc.meta.get("total_tasks", 0)),
            "overall_progress": str(doc.meta.get("overall_progress", 0)),
            "state_version": str(doc.meta.get("state_version", 0)),
            "last_updated_by": str(doc.meta.get("last_updated_by", "agent")),
            "last_updated_at": str(doc.meta.get("last_updated_at", _now_iso())),
        }
        for req_id, item in sorted(doc.items.items()):
            parser[req_id] = {
                "title": item.title,
                "category": item.category,
                "status": item.status,
                "progress": str(item.progress),
                "qa_status": item.qa_status,
                "qa_score": str(item.qa_score),
                "qa_rework_count": str(item.qa_rework_count),
                "dev_note": item.dev_note,
                "qa_diff_note": item.qa_diff_note,
                "last_updated_by": item.last_updated_by,
                "last_updated_at": item.last_updated_at,
            }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            parser.write(f)

    def apply_spec_reset(
        self, spec: SpecDocument, updated_by: str = "cursor"
    ) -> tuple[StatusDocument, dict[str, list[str]]]:
        """SPEC_RESET: 요건 기준으로 상태 항목을 동기화하고 diff를 반환."""
        with self._lock:
            current = self.load() if self._doc is None else self._doc
            old_ids = set(current.items.keys())
            new_ids = set(spec.items.keys())
            diff = {
                "added": sorted(new_ids - old_ids),
                "removed": sorted(old_ids - new_ids),
                "changed": [],
            }

            new_items: dict[str, StatusItem] = {}
            for req_id, sitem in spec.items.items():
                if req_id in current.items:
                    existing = deepcopy(current.items[req_id])
                    if (
                        existing.title != sitem.title
                        or existing.category != sitem.category
                    ):
                        diff["changed"].append(req_id)
                    existing.title = sitem.title
                    existing.category = sitem.category
                    existing.priority = sitem.priority
                    existing.spec_ref = sitem.spec_ref
                    existing.acceptance_criteria = sitem.acceptance_criteria
                    existing.target_files = sitem.target_files
                    existing.last_updated_by = updated_by
                    existing.last_updated_at = _now_iso()
                    new_items[req_id] = existing
                else:
                    new_items[req_id] = StatusItem(
                        req_id=req_id,
                        title=sitem.title,
                        category=sitem.category,
                        status="TODO",
                        progress=0,
                        priority=sitem.priority,
                        spec_ref=sitem.spec_ref,
                        acceptance_criteria=sitem.acceptance_criteria,
                        target_files=sitem.target_files,
                        last_updated_by=updated_by,
                        last_updated_at=_now_iso(),
                    )

            doc = StatusDocument(
                meta={
                    **current.meta,
                    "project_name": spec.meta.get(
                        "project_name", current.meta.get("project_name", "")
                    ),
                },
                items=new_items,
            )
            # 명세 메타 키를 항목에 반영해 두기 위해 메모리에 보관
            for req_id, sitem in spec.items.items():
                new_items[req_id].priority = sitem.priority
                new_items[req_id].spec_ref = sitem.spec_ref
                new_items[req_id].acceptance_criteria = sitem.acceptance_criteria
                new_items[req_id].target_files = sitem.target_files

            self.save(doc, updated_by=updated_by)
            return doc, diff

    def update_from_cursor(
        self,
        req_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        dev_note: str | None = None,
        expected_version: int | None = None,
        updated_by: str = "cursor",
    ) -> StatusDocument:
        """Cursor STATUS_UPDATE. progress는 0~60만 허용."""
        with self._lock:
            doc = self._require_doc()
            self._check_version(doc, expected_version)
            if req_id not in doc.items:
                raise StatusValidationError(f"알 수 없는 항목: {req_id}", section=req_id)
            item = doc.items[req_id]
            if progress is not None:
                if progress < 0 or progress > CURSOR_PROGRESS_MAX:
                    raise StatusValidationError(
                        f"Cursor는 progress 0~{CURSOR_PROGRESS_MAX}만 설정 가능: {progress}",
                        section=req_id,
                    )
                if 61 <= progress <= 79:
                    raise StatusValidationError(
                        f"progress 61~79 저장 불가: {progress}", section=req_id
                    )
                item.progress = progress
            if status is not None:
                if status not in STATUS_VALUES - {"VERIFIED"}:
                    # Cursor는 VERIFIED 직접 설정 불가
                    if status == "VERIFIED":
                        raise StatusValidationError(
                            "Cursor는 VERIFIED를 설정할 수 없음", section=req_id
                        )
                    if status not in STATUS_VALUES:
                        raise StatusValidationError(
                            f"잘못된 status: {status}", section=req_id
                        )
                item.status = status
            if dev_note is not None:
                item.dev_note = dev_note
            item.last_updated_by = updated_by
            item.last_updated_at = _now_iso()
            return self.save(doc, updated_by=updated_by)

    def apply_qa_result(
        self,
        req_id: str,
        *,
        qa_status: str,
        qa_score: int = 0,
        qa_diff_note: str = "",
        expected_version: int | None = None,
        updated_by: str = "grok",
    ) -> StatusDocument:
        """그록 봇 QA_RESULT 적용."""
        with self._lock:
            doc = self._require_doc()
            self._check_version(doc, expected_version)
            if req_id not in doc.items:
                raise StatusValidationError(f"알 수 없는 항목: {req_id}", section=req_id)
            if qa_status not in QA_STATUS_VALUES:
                raise StatusValidationError(
                    f"잘못된 qa_status: {qa_status}", section=req_id
                )
            item = doc.items[req_id]
            item.qa_status = qa_status
            item.qa_score = max(0, min(100, int(qa_score)))
            if qa_diff_note:
                item.qa_diff_note = qa_diff_note

            if qa_status == "PASSED":
                item.progress = compute_qa_progress(item.qa_score)
                item.status = "IN_REVIEW"  # 발주자 최종 승인 대기
            elif qa_status == "FAILED_REWORK":
                item.progress = CURSOR_PROGRESS_MAX
                item.status = "REWORK_REQUESTED"
                item.qa_rework_count = int(item.qa_rework_count) + 1

            item.last_updated_by = updated_by
            item.last_updated_at = _now_iso()
            return self.save(doc, updated_by=updated_by)

    def apply_user_command_state(
        self,
        req_ids: list[str],
        command_type: str,
        note: str = "",
        updated_by: str = "user",
    ) -> StatusDocument:
        """발주자 UI 명령에 따른 상태 전환."""
        with self._lock:
            doc = self._require_doc()
            for req_id in req_ids:
                if req_id not in doc.items:
                    raise StatusValidationError(
                        f"알 수 없는 항목: {req_id}", section=req_id
                    )
                item = doc.items[req_id]
                if command_type == "extra_verify":
                    item.status = "IN_REVIEW"
                    item.qa_status = "PENDING"
                    if note:
                        item.qa_diff_note = note
                elif command_type == "rework":
                    item.status = "REWORK_REQUESTED"
                    if note:
                        item.qa_diff_note = note
                elif command_type == "qa_reeval":
                    item.qa_status = "PENDING"
                    if note:
                        item.qa_diff_note = note
                elif command_type == "final_approve":
                    if item.qa_status != "PASSED":
                        raise StatusValidationError(
                            f"최종 승인은 qa_status=PASSED만 가능: {req_id}",
                            section=req_id,
                        )
                    item.status = "VERIFIED"
                else:
                    raise StatusValidationError(f"알 수 없는 명령: {command_type}")
                item.last_updated_by = updated_by
                item.last_updated_at = _now_iso()
            return self.save(doc, updated_by=updated_by)

    def replace_from_external_parse(self, text: str) -> StatusDocument:
        """감시 루프가 외부 수정 파일을 파싱해 반영할 때 사용."""
        with self._lock:
            doc = self._parse(text)
            self._doc = doc
            return doc

    def _require_doc(self) -> StatusDocument:
        if self._doc is None:
            return self.load()
        return self._doc

    @staticmethod
    def _check_version(doc: StatusDocument, expected: int | None) -> None:
        if expected is None:
            return
        current = int(doc.meta.get("state_version", 0))
        if expected != current:
            raise StatusValidationError(
                f"state_version 불일치: expected={expected}, current={current}"
            )
