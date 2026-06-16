from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    A3_DIFF_LEAVE_THRESHOLD,
    A3_NET_VALUE_LABEL,
    amounts_close,
    parse_threshold_amount,
)
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_check_with_a3_row"


def _is_net_value_line(account_label: str) -> bool:
    return A3_NET_VALUE_LABEL in (account_label or "")


def _diff_is_material(diff_amt: Decimal) -> bool:
    return abs(diff_amt) >= A3_DIFF_LEAVE_THRESHOLD


def check_lead_check_with_a3_row(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """Check with A3：仅核对净值行；|Diff|<1 视为尾差；重大非零 Diff 须有 Notes。"""
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

    net_lines = [ln for ln in cw.lines if _is_net_value_line(ln.account_label)]
    if not net_lines:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="check_with_a3",
                severity=Severity.WARN,
                message="引导主表未识别净值行，无法自动核对 Check with A3",
                suggestion="确认引导表含「净值」行及 Check with A3 / Diff",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    issues: list[QcIssue] = []
    for line in net_lines:
        diff_amt = parse_threshold_amount(line.diff_value)
        if diff_amt is None:
            continue
        if diff_amt == 0 or not _diff_is_material(diff_amt):
            continue
        mov_amt = parse_threshold_amount(line.movement_value)
        a3_amt = parse_threshold_amount(line.a3_value)
        details = [f"Diff={diff_amt}"]
        if (
            mov_amt is not None
            and a3_amt is not None
            and not amounts_close(mov_amt, a3_amt, ref=max(abs(mov_amt), abs(a3_amt)))
        ):
            details.append(f"引导表金额={mov_amt}，A3金额={a3_amt}")
        if is_blank(cw.notes_text):
            details.append("未识别到Notes说明")
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=f"check_with_a3_diff:{line.account_label}",
                severity=Severity.FAIL,
                message=f"「{line.account_label}」Check with A3/Diff 核对不一致：" + "；".join(details),
                suggestion="核对 A3 与引导表净值，并在 Notes 中说明差异原因。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=cw.diff_source_row or cw.check_source_row,
            )
        )

    return issues
