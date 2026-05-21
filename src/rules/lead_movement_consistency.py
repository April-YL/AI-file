from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import amounts_close, movement_amount_for_row
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount

RULE_ID = "lead_movement_consistency"


def check_lead_movement_consistency(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """审定期末 − 上期审定 ≈ 变动金额（容差 0.01）。"""
    if lead is None or not lead.source_sheet or not lead.movement_rows:
        return []

    issues: list[QcIssue] = []
    for row in lead.movement_rows:
        ending = parse_amount(row.values.get("audited_ending"))
        opening = parse_amount(row.values.get("py_audited"))
        movement = movement_amount_for_row(row.values)
        if ending is None or opening is None or movement is None:
            continue
        implied = ending - opening
        if not amounts_close(implied, movement, ref=max(abs(ending), abs(movement), abs(implied))):
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=f"movement:{row.account_label}",
                    severity=Severity.FAIL,
                    message=(
                        f"「{row.account_label}」变动金额（{movement}）与"
                        f"审定期末−上期审定（{implied}）不一致"
                    ),
                    suggestion="核对变动金额公式或期初/期末审定数",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                    source_row=row.source_row,
                )
            )
    return issues
