"""多期底稿工作表路由：优先当期 sheet，降低上年（-24）与残缺后缀表权重。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")

_PRIOR_YEAR_SUFFIX = re.compile(r"-24\s*$", re.I)
_TRAILING_STUB_SUFFIX = re.compile(r".+-\s*$")


def infer_audit_year_end_from_path(path: str | Path | None) -> int | None:
    """从底稿文件名推断审计截止年（如 ``...20251231...`` → 2025）。"""
    if path is None:
        return None
    match = re.search(r"(20\d{2})1231", Path(path).name)
    return int(match.group(1)) if match else None


def sheet_period_sort_key(
    sheet_name: str,
    *,
    confidence: float = 0.0,
    source_path: str | Path | None = None,
) -> tuple[float, float, str]:
    """排序键：(期别惩罚, -置信度, 规范化名称)；越小越优先。"""
    name = sheet_name.strip()
    penalty = 0.0
    if _PRIOR_YEAR_SUFFIX.search(name):
        penalty += 2.0
    elif _TRAILING_STUB_SUFFIX.search(name) and not _PRIOR_YEAR_SUFFIX.search(name):
        penalty += 1.0

    audit_year = infer_audit_year_end_from_path(source_path)
    if audit_year:
        for year_text in re.findall(r"(20\d{2})", name):
            sheet_year = int(year_text)
            if sheet_year <= audit_year - 1:
                penalty += 1.5
                break

    return (penalty, -confidence, name.lower())


def sort_sheet_candidates(
    candidates: list[T],
    *,
    name: Callable[[T], str],
    confidence: Callable[[T], float] = lambda _: 0.0,
    source_path: str | Path | None = None,
) -> list[T]:
    return sorted(
        candidates,
        key=lambda c: sheet_period_sort_key(
            name(c),
            confidence=confidence(c),
            source_path=source_path,
        ),
    )


def choose_sheet_candidate(
    candidates: list[T],
    *,
    name: Callable[[T], str],
    confidence: Callable[[T], float] = lambda _: 0.0,
    source_path: str | Path | None = None,
) -> T | None:
    ordered = sort_sheet_candidates(
        candidates,
        name=name,
        confidence=confidence,
        source_path=source_path,
    )
    return ordered[0] if ordered else None
