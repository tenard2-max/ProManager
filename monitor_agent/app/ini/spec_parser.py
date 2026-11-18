"""요건 INI(spec.ini) 파싱 및 스키마 검증."""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schemas import META_REQUIRED, PRIORITIES, REQ_REQUIRED, SpecValidationError


@dataclass
class SpecItem:
    req_id: str
    title: str
    category: str
    priority: str
    spec_ref: str
    acceptance_criteria: str
    target_files: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "req_id": self.req_id,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "spec_ref": self.spec_ref,
            "acceptance_criteria": self.acceptance_criteria,
            "target_files": self.target_files,
        }


@dataclass
class SpecDocument:
    meta: dict[str, str]
    items: dict[str, SpecItem] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": dict(self.meta),
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "errors": list(self.errors),
        }


def _read_text(path_or_text: str | Path, *, is_path: bool) -> str:
    if is_path:
        path = Path(path_or_text)
        raw = path.read_bytes()
        # UTF-8 BOM 허용
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw[3:].decode("utf-8")
        return raw.decode("utf-8")
    return str(path_or_text)


def _parse_config(text: str) -> configparser.ConfigParser:
    # acceptance_criteria 등의 '%' (예: 90%)가 보간 문법으로 오인되지 않도록 끔
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # 키 대소문자 유지
    try:
        parser.read_string(text)
    except configparser.DuplicateSectionError as exc:
        raise SpecValidationError(
            f"섹션 ID 중복: {exc.section}", section=exc.section
        ) from exc
    return parser


def _validate_meta(section: configparser.SectionProxy) -> dict[str, str]:
    missing = [k for k in META_REQUIRED if k not in section or not section[k].strip()]
    if missing:
        raise SpecValidationError(
            f"META 필수 키 누락: {', '.join(missing)}", section="META"
        )
    return {k: section[k].strip() for k in section}


def _validate_req(
    req_id: str, section: configparser.SectionProxy
) -> SpecItem | list[str]:
    errors: list[str] = []
    for key in REQ_REQUIRED:
        if key not in section or not str(section.get(key, "")).strip():
            errors.append(f"{req_id}: 필수 키 누락 또는 빈 값: {key}")

    priority = section.get("priority", "").strip()
    if priority and priority not in PRIORITIES:
        errors.append(f"{req_id}: priority는 HIGH|MEDIUM|LOW 중 하나여야 함: {priority}")

    if errors:
        return errors

    return SpecItem(
        req_id=req_id,
        title=section["title"].strip(),
        category=section["category"].strip(),
        priority=priority,
        spec_ref=section["spec_ref"].strip(),
        acceptance_criteria=section["acceptance_criteria"].strip(),
        target_files=section["target_files"].strip(),
    )


def parse_spec_text(text: str, *, strict: bool = True) -> SpecDocument:
    """요건 INI 텍스트를 파싱·검증한다.

    strict=True면 META 또는 치명 오류 시 SpecValidationError를 발생시킨다.
    개별 REQ 섹션 오류는 errors에 담고 해당 섹션만 거부한다.
    """
    parser = _parse_config(text)
    sections = list(parser.sections())

    if "META" not in sections:
        raise SpecValidationError("META 섹션이 없습니다.", section="META")

    meta = _validate_meta(parser["META"])
    doc = SpecDocument(meta=meta)
    seen: set[str] = set()

    for name in sections:
        if name == "META":
            continue
        if not name.startswith("REQ_"):
            doc.errors.append(f"알 수 없는 섹션 무시: {name}")
            continue
        if name in seen:
            msg = f"섹션 ID 중복: {name}"
            doc.errors.append(msg)
            if strict:
                raise SpecValidationError(msg, section=name)
            continue
        seen.add(name)

        result = _validate_req(name, parser[name])
        if isinstance(result, list):
            doc.errors.extend(result)
            continue
        doc.items[name] = result

    return doc


def parse_spec_ini(path: str | Path, *, strict: bool = True) -> SpecDocument:
    text = _read_text(path, is_path=True)
    return parse_spec_text(text, strict=strict)
