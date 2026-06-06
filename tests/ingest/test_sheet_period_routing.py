"""多期 sheet 路由单元测试。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingest.sheet_period_routing import (
    choose_sheet_candidate,
    infer_audit_year_end_from_path,
    sheet_period_sort_key,
    sort_sheet_candidates,
)


@dataclass
class _Stub:
    sheet_name: str
    confidence: float


def test_infer_audit_year_from_filename():
    path = Path("E:/case/ABC20251231底稿.xlsx")
    assert infer_audit_year_end_from_path(path) == 2025
    assert infer_audit_year_end_from_path(None) is None


def test_prior_year_suffix_penalty():
    current = sheet_period_sort_key("K.01", confidence=0.9)
    prior = sheet_period_sort_key("K.01-24", confidence=0.9)
    assert current < prior


def test_stub_suffix_penalty_between_current_and_prior():
    current = sheet_period_sort_key("FA list", confidence=0.9)
    stub = sheet_period_sort_key("FA list-", confidence=0.9)
    prior = sheet_period_sort_key("FA list-24", confidence=0.9)
    assert current < stub < prior


def test_choose_current_over_prior_when_confidence_equal():
    candidates = [
        _Stub("汇总-24", 0.95),
        _Stub("汇总", 0.95),
    ]
    chosen = choose_sheet_candidate(
        candidates,
        name=lambda c: c.sheet_name,
        confidence=lambda c: c.confidence,
    )
    assert chosen is not None
    assert chosen.sheet_name == "汇总"


def test_confidence_breaks_tie_within_same_period():
    candidates = [
        _Stub("K.01", 0.85),
        _Stub("K.01 Agree SL to GL", 0.95),
    ]
    ordered = sort_sheet_candidates(
        candidates,
        name=lambda c: c.sheet_name,
        confidence=lambda c: c.confidence,
    )
    assert ordered[0].sheet_name == "K.01 Agree SL to GL"


def test_workbook_year_boosts_penalty_for_embedded_old_year():
    path = Path("客户20251231.xlsx")
    current = sheet_period_sort_key(
        "K.01",
        confidence=0.9,
        source_path=path,
    )
    old = sheet_period_sort_key(
        "K.01 2024",
        confidence=0.9,
        source_path=path,
    )
    assert current < old
