from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    exceeds_volatility_threshold,
    movement_amount_for_row,
    parse_threshold_amount,
)
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_expectation_vs_movement_review"

_NO_MAJOR_CHANGE_HINTS = (
    "无重大",
    "无明显",
    "无异常",
    "无波动",
    "不重大",
    "较小",
    "稳定",
    "no significant",
    "no material",
)


def _parse_percent(value: str | None) -> Decimal | None:
    if is_blank(value):
        return None
    text = str(value).strip().replace("%", "")
    try:
        val = Decimal(text)
    except Exception:
        return None
    if val > 1:
        val = val / Decimal("100")
    return val


def _has_no_major_change_expectation(lead: LeadSheetDataset) -> bool:
    for row in lead.expectations:
        text = f"{row.account_change or ''} {row.expectation or ''}".lower()
        if any(hint in text for hint in _NO_MAJOR_CHANGE_HINTS):
            return True
    return False


def _movement_pct(row_values: dict[str, str | None]) -> Decimal | None:
    return _parse_percent(row_values.get("movement_pct"))


def check_lead_expectation_vs_movement_review(
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    """Flag cases where expectations say no major change but actual movement exceeds thresholds."""
    if lead is None or not lead.source_sheet or not lead.expectations or not lead.movement_rows:
        return []
    if not _has_no_major_change_expectation(lead):
        return []

    vol_amount = parse_threshold_amount(lead.volatility.amount) if lead.volatility else None
    vol_percent = _parse_percent(lead.volatility.percent) if lead.volatility else None
    if vol_amount is None and vol_percent is None:
        return []

    triggered: list[str] = []
    first_row: int | None = None
    for row in lead.movement_rows:
        movement = movement_amount_for_row(row.values)
        pct = _movement_pct(row.values)
        if exceeds_volatility_threshold(
            movement,
            pct,
            vol_amount=vol_amount,
            vol_percent=vol_percent,
        ):
            triggered.append(row.account_label)
            first_row = first_row or row.source_row

    if not triggered:
        return []

    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field="expectation_vs_movement",
            severity=Severity.NEED_REVIEW,
            message=(
                "Lead 预期分析存在“无重大/无异常波动”口径，但主表实际波动超过阈值："
                f"{'、'.join(triggered[:5])}"
            ),
            suggestion="复核预期是否需要更新，或在波动说明区解释实际波动与预期的关系。",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
            source_row=first_row,
        )
    ]
