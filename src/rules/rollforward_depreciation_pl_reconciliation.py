from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount

RULE_ID = "rollforward_depreciation_pl_reconciliation"
_AMOUNT_TOL = Decimal("0.01")


def _source_sheet(rollforward: RollforwardSheetDataset | None) -> str:
    return (
        rollforward.source_sheet
        if rollforward and rollforward.source_sheet
        else "K.01 Agree SL to GL"
    )


def _sad_from_lead(lead: LeadSheetDataset | None) -> Decimal | None:
    if lead is None:
        return None
    sad = parse_amount(field_values(lead).get("sad"))
    if sad is None or sad <= 0:
        return None
    return sad


def _issue(
    *,
    rollforward: RollforwardSheetDataset | None,
    severity: Severity,
    field: str,
    message: str,
    suggestion: str,
    source_row: int | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=RULE_ID,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.01",
        source_sheet=_source_sheet(rollforward),
        source_row=source_row,
    )


def check_rollforward_depreciation_pl_reconciliation(
    rollforward: RollforwardSheetDataset | None,
    *,
    lead: LeadSheetDataset | None = None,
) -> list[QcIssue]:
    """K.01 表4：折旧费用与利润表科目核对。

    差异为 0 或不超过 SAD 时通过；超过 SAD 时需要 Notes。
    """
    if rollforward is None:
        return []

    if not rollforward.section_presence.get("b5_table4_depreciation_pl"):
        return [
            _issue(
                rollforward=rollforward,
                severity=Severity.NEED_REVIEW,
                field="b5_table4_depreciation_pl",
                message="未可靠识别 K.01 表4（折旧费用与利润表科目核对）",
                suggestion="请人工确认 K.01 是否保留表4，并核对折旧费用是否已与利润表/TB一致。",
            )
        ]

    if rollforward.table4_difference is None:
        return [
            _issue(
                rollforward=rollforward,
                severity=Severity.NEED_REVIEW,
                field="table4_difference",
                message="已识别 K.01 表4，但未读取到折旧费用与利润表科目的差异金额",
                suggestion="请检查表4是否有“合计”“累计折旧科目-本年计提”“差异”等行，或确认公式是否被模板变体影响。",
                source_row=rollforward.table4_pl_total_row
                or rollforward.table4_rollforward_depreciation_row,
            )
        ]

    diff = rollforward.table4_difference
    if abs(diff) <= _AMOUNT_TOL:
        return []

    sad = _sad_from_lead(lead)
    if sad is None:
        return [
            _issue(
                rollforward=rollforward,
                severity=Severity.NEED_REVIEW,
                field="sad",
                message="K.01 表4存在折旧费用差异，但未能从 K.00 Lead 可靠读取 SAD",
                suggestion="请先确认 K.00 Lead 的 SAD（名义金额）是否填写正确，再判断表4差异是否需要 Notes 解释。",
                source_row=rollforward.table4_difference_row,
            )
        ]

    if abs(diff) <= sad:
        return []

    if rollforward.table4_notes_text_present:
        note_text = rollforward.table4_notes_text or ""
        compact_note = note_text.replace(" ", "")
        if "小于SAD" in compact_note or "低于SAD" in compact_note or "未超过SAD" in compact_note:
            return [
                _issue(
                    rollforward=rollforward,
                    severity=Severity.FAIL,
                    field="table4_notes_text",
                    message=(
                        "K.01 表4折旧费用与利润表科目核对差异超过 SAD，"
                        f"但 Notes 描述为差异小于/未超过 SAD：差异={diff}，SAD={sad}"
                    ),
                    suggestion="请复核表4差异金额与 Notes 说明是否一致；若差异确超过 SAD，应补充进一步分析和处理结论。",
                    source_row=rollforward.table4_notes_row or rollforward.table4_difference_row,
                )
            ]
        return [
            _issue(
                rollforward=rollforward,
                severity=Severity.NEED_REVIEW,
                field="table4_notes_text",
                message=(
                    "K.01 表4折旧费用与利润表科目核对存在超过 SAD 的差异，"
                    f"且已填写 Notes：差异={diff}，SAD={sad}"
                ),
                suggestion="请人工判断 Notes 是否充分说明差异原因、风险影响及处理结论。",
                source_row=rollforward.table4_notes_row or rollforward.table4_difference_row,
            )
        ]

    return [
        _issue(
            rollforward=rollforward,
            severity=Severity.FAIL,
            field="table4_notes_text",
            message=(
                "K.01 表4折旧费用与利润表科目核对存在超过 SAD 的差异，"
                f"但未读取到 Notes 解释：差异={diff}，SAD={sad}"
            ),
            suggestion="请在表4后方或 Notes 区补充差异说明；Notes 的具体符号/格式不限制，但应能说明差异原因或处理结论。",
            source_row=rollforward.table4_difference_row,
        )
    ]
