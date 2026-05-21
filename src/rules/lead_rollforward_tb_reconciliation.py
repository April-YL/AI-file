from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.lead_common import (
    amounts_close,
    lead_book_balance,
    movement_field_key,
)
from rules.models import QcIssue, Severity

RULE_ID = "lead_rollforward_tb_reconciliation"


def check_lead_rollforward_tb_reconciliation(
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    """引导表期末账面数与 K.01 后推 TB 合计一致。"""
    if lead is None or not lead.source_sheet:
        return []
    if rollforward is None or not rollforward.ending_totals:
        return []

    issues: list[QcIssue] = []
    for row in lead.movement_rows:
        field_key = movement_field_key(row.account_label)
        if field_key is None:
            continue
        lead_amt = lead_book_balance(row.values)
        rf_amt = rollforward.ending_totals.get(field_key)
        if lead_amt is None or rf_amt is None:
            continue
        if not amounts_close(lead_amt, rf_amt, ref=max(abs(lead_amt), abs(rf_amt))):
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=f"{field_key}|{row.account_label}",
                    severity=Severity.FAIL,
                    message=(
                        f"Lead「{row.account_label}」期末数（{lead_amt}）与 K.01 后推"
                        f"（{rf_amt}）不一致"
                    ),
                    suggestion="核对引导表 link 与后推 TB 列公式",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                    source_row=row.source_row,
                )
            )
    return issues
