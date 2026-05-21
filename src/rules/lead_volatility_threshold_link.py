from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    amounts_close,
    effective_overall_threshold,
    field_values,
    parse_threshold_amount,
    skip_cra_module,
)
from rules.models import QcIssue, Severity

RULE_ID = "lead_volatility_threshold_link"


def check_lead_volatility_threshold_link(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """波动幅度金额应与整体 TT（标准版）或 TE（简版）一致。"""
    if lead is None or not lead.source_sheet:
        return []

    vol = lead.volatility
    if vol is None:
        return []

    vol_amt = parse_threshold_amount(vol.amount)
    if vol_amt is None:
        return []

    if skip_cra_module(lead):
        target = parse_threshold_amount(field_values(lead).get("te"))
        label = "TE"
    else:
        target = effective_overall_threshold(lead.cra_rows)
        label = "整体 TT"

    if target is None:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="volatility.amount",
                severity=Severity.WARN,
                message=f"无法确定{label}，未核对波动幅度金额 link",
                suggestion="补充 CRA/TT 或 TE 后重跑",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    if not amounts_close(vol_amt, target, ref=target):
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="volatility.amount",
                severity=Severity.WARN,
                message=(
                    f"波动幅度金额（{vol_amt}）与{label}（{target}）明显不一致"
                ),
                suggestion=f"确认波动幅度金额公式 link {label}",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=vol.source_row_amount,
            )
        ]

    return []
