"""Phase 1: 요건 INI 파서 검증."""

from __future__ import annotations

import pytest

from app.ini.schemas import SpecValidationError
from app.ini.spec_parser import parse_spec_text


VALID_SPEC = """
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
acceptance_criteria = must pass unit tests
target_files = a.py
"""


def test_parse_valid_spec():
    doc = parse_spec_text(VALID_SPEC)
    assert doc.meta["project_name"] == "Demo"
    assert "REQ_001" in doc.items
    assert doc.items["REQ_001"].priority == "HIGH"
    assert not doc.errors


def test_reject_missing_meta_key():
    bad = VALID_SPEC.replace("submitted_by = cursor\n", "")
    with pytest.raises(SpecValidationError):
        parse_spec_text(bad)


def test_reject_empty_acceptance_criteria():
    bad = VALID_SPEC.replace(
        "acceptance_criteria = must pass unit tests",
        "acceptance_criteria = ",
    )
    doc = parse_spec_text(bad, strict=False)
    assert "REQ_001" not in doc.items
    assert any("acceptance_criteria" in e for e in doc.errors)


def test_reject_bad_priority():
    bad = VALID_SPEC.replace("priority = HIGH", "priority = URGENT")
    doc = parse_spec_text(bad, strict=False)
    assert "REQ_001" not in doc.items
    assert any("priority" in e for e in doc.errors)


def test_reject_duplicate_section():
    dup = VALID_SPEC + """
[REQ_001]
title = Dup
category = Core
priority = LOW
spec_ref = 1.2
acceptance_criteria = x
target_files = b.py
"""
    with pytest.raises(SpecValidationError, match="중복"):
        parse_spec_text(dup, strict=False)
