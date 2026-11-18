"""INI 스키마 상수 및 검증 오류 타입."""

from __future__ import annotations

from typing import Final

META_REQUIRED: Final[tuple[str, ...]] = (
    "project_name",
    "spec_version",
    "submitted_by",
    "submitted_at",
)

REQ_REQUIRED: Final[tuple[str, ...]] = (
    "title",
    "category",
    "priority",
    "spec_ref",
    "acceptance_criteria",
    "target_files",
)

PRIORITIES: Final[frozenset[str]] = frozenset({"HIGH", "MEDIUM", "LOW"})

STATUS_VALUES: Final[frozenset[str]] = frozenset(
    {"TODO", "IN_PROGRESS", "IN_REVIEW", "REWORK_REQUESTED", "VERIFIED"}
)

QA_STATUS_VALUES: Final[frozenset[str]] = frozenset(
    {"PENDING", "PASSED", "FAILED_REWORK"}
)

STATUS_META_KEYS: Final[tuple[str, ...]] = (
    "project_name",
    "total_tasks",
    "overall_progress",
    "state_version",
    "last_updated_by",
    "last_updated_at",
)

STATUS_ITEM_KEYS: Final[tuple[str, ...]] = (
    "title",
    "category",
    "status",
    "progress",
    "qa_status",
    "qa_score",
    "qa_rework_count",
    "dev_note",
    "qa_diff_note",
    "last_updated_by",
    "last_updated_at",
)


class SpecValidationError(Exception):
    """요건 INI 검증 실패."""

    def __init__(self, message: str, section: str | None = None) -> None:
        self.section = section
        super().__init__(message)


class StatusValidationError(Exception):
    """상태 INI 검증 실패."""

    def __init__(self, message: str, section: str | None = None) -> None:
        self.section = section
        super().__init__(message)
