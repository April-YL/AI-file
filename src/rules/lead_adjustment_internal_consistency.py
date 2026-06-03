from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_adjustment_gating import should_run_strict_total_check
from rules.lead_common import amounts_close, parse_threshold_amount
from rules.models import QcIssue, Severity

RULE_ID = "lead_adjustment_internal_consistency"

_ADJUSTMENT_ROLES = ("book_adjustment", "audit_adjustment")


def _main_adjustment_amounts(lead: LeadSheetDataset) -> list[tuple[str, Decimal, int]]:
    amounts: list[tuple[str, Decimal, int]] = []
    for row in lead.movement_rows:
        for role in _ADJUSTMENT_ROLES:
            amt = parse_threshold_amount(row.values.get(role))
            if amt is not None and amt != 0:
                amounts.append((row.account_label, amt, row.source_row))
    return amounts


def _summary_amounts(lead: LeadSheetDataset) -> list[Decimal]:
    amounts: list[Decimal] = []
    for row in lead.adjustment_rows:
        for cell in row.raw_cells:
            amt = parse_threshold_amount(cell)
            if amt is not None and amt != 0:
                amounts.append(amt)
    return amounts


def check_lead_adjustment_internal_consistency(
    lead: LeadSheetDataset | None,
    *,
    strict_total: bool | None = None,
    layout_result: dict | None = None,
    extracted_rows: list[dict] | None = None,
) -> list[QcIssue]:
    """Compare Lead movement-table adjustment columns with the Lead adjustment summary only."""
    if lead is None or not lead.source_sheet:
        return []

    if strict_total is None:
        strict_total = should_run_strict_total_check(
            lead,
            layout_result=layout_result,
            extracted_rows=extracted_rows,
        )

    main_amounts = _main_adjustment_amounts(lead)
    summary_rows = [
        r
        for r in lead.adjustment_rows
        if not _is_no_adjustment_conclusion(r.raw_cells)
        and not _is_non_adjustment_note(r.raw_cells)
    ]
    summary_amounts = _summary_amounts(lead)
    issues: list[QcIssue] = []

    if main_amounts and not summary_rows:
        labels = "、".join(label for label, _, _ in main_amounts[:5])
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="adjustment_summary",
                severity=Severity.FAIL,
                message=f"Lead 主表存在调整金额，但调整事项汇总表未识别到记录：{labels}",
                suggestion="在 Lead 调整事项汇总表补充对应调整记录，或清理主表调整列。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=main_amounts[0][2],
            )
        )
        return issues

    if summary_rows and not main_amounts:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="movement_adjustments",
                severity=Severity.WARN,
                message="Lead 调整事项汇总表存在记录，但主表账表/审计调整列未识别到调整金额",
                suggestion="复核调整汇总是否应回填至 Lead 主表调整列，或确认该汇总记录无需影响主表。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=summary_rows[0].source_row,
            )
        )
        return issues

    if not strict_total or not main_amounts or not summary_amounts:
        return issues

    main_total = sum((amt for _, amt, _ in main_amounts), Decimal("0"))
    summary_total = sum(summary_amounts, Decimal("0"))
    if not amounts_close(main_total, summary_total, ref=max(abs(main_total), abs(summary_total))):
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="adjustment_amount",
                severity=Severity.NEED_REVIEW,
                message=(
                    f"Lead 主表调整列合计（{main_total}）与调整事项汇总表可识别金额合计"
                    f"（{summary_total}）不一致"
                ),
                suggestion="复核 Lead 主表调整列与调整事项汇总表金额是否使用同一口径。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=summary_rows[0].source_row,
            )
        )
    return issues


def _is_no_adjustment_conclusion(cells: list[str | None]) -> bool:
    text = "".join(str(c) for c in cells if c)
    compact = (
        text.replace(" ", "")
        .replace("　", "")
        .replace("。", "")
        .replace(".", "")
        .lower()
    )
    markers = (
        "本年度不涉及审计调整",
        "本年不涉及审计调整",
        "本期不涉及审计调整",
        "不涉及审计调整",
        "无审计调整",
        "无调整事项",
        "不涉及调整事项",
    )
    return any(m.lower() in compact for m in markers)


def _is_non_adjustment_note(cells: list[str | None]) -> bool:
    text_cells = [str(c) for c in cells if c]
    if len(text_cells) != 1:
        return False
    text = text_cells[0]
    compact = (
        text.replace(" ", "")
        .replace("　", "")
        .replace("。", "")
        .replace(".", "")
        .lower()
    )
    return (
        compact.startswith("nb")
        and ("te" in compact or "sad" in compact)
    ) or ("执行阶段" in text and "审定阶段" in text and ("TE" in text or "SAD" in text))
