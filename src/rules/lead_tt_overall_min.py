from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    assertion_tt_values,
    amounts_close,
    overall_tt_value,
    skip_cra_module,
)
from rules.models import QcIssue, Severity

RULE_ID = "lead_tt_overall_min"


def check_lead_tt_overall_min(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """整体 TT 应等于各认定 TT 的最小值（排除 0）。"""
    if lead is None or not lead.source_sheet or skip_cra_module(lead):
        return []
    if not lead.cra_rows:
        return []

    tts = assertion_tt_values(lead.cra_rows)
    if not tts:
        return []

    expected = min(tts)
    overall = overall_tt_value(lead.cra_rows)
    if overall is None:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="tt_overall",
                severity=Severity.WARN,
                message="Lead 未摘录到整体 Threshold（所有相关认定）",
                suggestion="在 CRA/TT 区维护整体 TT，或确认其等于各认定 TT 的最小值",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    if overall == 0:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="tt_overall",
                severity=Severity.WARN,
                message="整体 Threshold 为 0，通常应大于 0",
                suggestion="按 GAM 与 CRA 表复核整体 TT 公式",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    if not amounts_close(overall, expected, ref=expected):
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="tt_overall",
                severity=Severity.FAIL,
                message=(
                    f"整体 TT（{overall}）与各认定 TT 最小值（{expected}）不一致"
                ),
                suggestion="将「所有相关认定」Threshold 调整为各认定 TT 的最小值（排除 0）",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    return []
