from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import is_affirmative
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_movement_notes_required"


def check_lead_movement_notes_required(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """波动或定性调查为「是」时须有 Notes。"""
    if lead is None or not lead.source_sheet or not lead.movement_rows:
        return []

    roles = {b.role for b in lead.movement_bindings}
    if "investigate_quantitative" not in roles and "investigate_qualitative" not in roles:
        return []

    issues: list[QcIssue] = []
    for row in lead.movement_rows:
        need_note = False
        flags: list[str] = []
        for role, label in (
            ("investigate_quantitative", "波动幅度判断"),
            ("investigate_qualitative", "定性判断"),
        ):
            if role not in roles:
                continue
            val = row.values.get(role)
            if is_affirmative(val):
                need_note = True
                flags.append(label)
        if need_note and is_blank(row.values.get("notes")):
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=f"notes:{row.account_label}",
                    severity=Severity.FAIL,
                    message=(
                        f"「{row.account_label}」{('/'.join(flags))}为是，但未填写 Notes"
                    ),
                    suggestion="补充 Notes 编号并在波动说明区展开分析",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                    source_row=row.source_row,
                )
            )
    return issues
