from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import amounts_close, parse_threshold_amount
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_check_with_a3_row"


def check_lead_check_with_a3_row(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """Check with A3：Diff 应为 0；非 0 须有 Notes 说明；引导表与 A3 行金额宜一致。"""
    if lead is None or not lead.source_sheet:
        return []

    if not lead.movement_rows:
        return []

    cw = lead.check_with_a3
    if cw is None:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="check_with_a3",
                severity=Severity.WARN,
                message="引导主表未识别 Check with A3 / Diff 行，无法自动核对 A3 差异",
                suggestion="在引导表四行下维护 Check with A3、Diff 及 Notes 说明",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    issues: list[QcIssue] = []
    nonzero_without_notes = False

    for line in cw.lines:
        diff_amt = parse_threshold_amount(line.diff_value)
        if diff_amt is None:
            continue
        if diff_amt == 0:
            continue
        nonzero_without_notes = True
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=f"diff:{line.account_label}",
                severity=Severity.FAIL,
                message=(
                    f"「{line.account_label}」A3 核对 Diff 为 {diff_amt}（应为 0）"
                ),
                suggestion="核对 A3 与引导表金额，或在 Notes 中说明差异原因",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=cw.diff_source_row,
            )
        )

        mov_amt = parse_threshold_amount(line.movement_value)
        a3_amt = parse_threshold_amount(line.a3_value)
        if mov_amt is not None and a3_amt is not None:
            if not amounts_close(mov_amt, a3_amt, ref=max(abs(mov_amt), abs(a3_amt))):
                issues.append(
                    QcIssue(
                        asset_id=None,
                        rule_id=RULE_ID,
                        field=f"a3:{line.account_label}",
                        severity=Severity.WARN,
                        message=(
                            f"「{line.account_label}」引导表金额（{mov_amt}）与 "
                            f"Check with A3 行（{a3_amt}）不一致"
                        ),
                        suggestion="确认 link A3 公式或更新 Check with A3 行",
                        procedure_code="K.00",
                        source_sheet=lead.source_sheet,
                        source_row=cw.check_source_row,
                    )
                )

    if nonzero_without_notes and is_blank(cw.notes_text):
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="notes",
                severity=Severity.FAIL,
                message="A3 核对存在非零 Diff，但未摘录到 Notes 说明",
                suggestion="在 Diff 行下方 Notes 区说明差异原因",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=cw.notes_source_row,
            )
        )

    return issues
