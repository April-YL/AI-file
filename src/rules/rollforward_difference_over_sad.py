from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount

RULE_ID = "rollforward_difference_over_sad"


def _source_sheet(rollforward: RollforwardSheetDataset | None) -> str:
    return (rollforward.source_sheet if rollforward and rollforward.source_sheet else "K.01 Agree SL to GL")


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


def check_rollforward_difference_over_sad(
    rollforward: RollforwardSheetDataset | None,
    *,
    lead: LeadSheetDataset | None = None,
) -> list[QcIssue]:
    """K.01 TB check 差异超过 SAD 时，应有 Notes 解释。

    规则只判断“是否需要说明、是否已有说明”。说明内容是否充分仍交给质检人员复核。
    """
    if rollforward is None:
        return []

    has_tb_area = rollforward.section_presence.get("b2_movement_tb_reconciliation", False)
    if not rollforward.tb_reconciliation_detected:
        if has_tb_area:
            return [
                _issue(
                    rollforward=rollforward,
                    severity=Severity.NEED_REVIEW,
                    field="tb_reconciliation",
                    source_row=rollforward.tb_difference_row,
                    message="K.01 已识别到变动/TB 区域，但未能可靠读取 TB check 结果",
                    suggestion="请人工确认 K.01 是否已完成与 TB/试算表核对；读不到时不要直接按 PASS 处理。",
                )
            ]
        return []

    if not rollforward.tb_difference_values:
        return [
            _issue(
                rollforward=rollforward,
                severity=Severity.NEED_REVIEW,
                field="tb_difference_values",
                message="K.01 已识别到 TB check，但未读取到差异金额",
                suggestion="请人工检查 TB check 差异列/差异行公式，确认是否存在超过 SAD 的差异。",
            )
        ]

    sad = _sad_from_lead(lead)
    if sad is None:
        return [
            _issue(
                rollforward=rollforward,
                severity=Severity.NEED_REVIEW,
                field="sad",
                source_row=rollforward.tb_difference_row,
                message="K.01 已读取到 TB check 差异，但未能从 K.00 Lead 可靠读取 SAD",
                suggestion="请先确认 K.00 Lead 的 SAD（名义金额）是否填写正确，再判断 K.01 差异是否需要调查说明。",
            )
        ]

    material_diffs = [d for d in rollforward.tb_difference_values if abs(d) > sad]
    if not material_diffs:
        return []

    max_diff = max(material_diffs, key=lambda d: abs(d))
    if rollforward.tb_notes_text_present:
        return [
            _issue(
                rollforward=rollforward,
                severity=Severity.NEED_REVIEW,
                field="tb_notes_text",
                source_row=rollforward.tb_notes_row or rollforward.tb_difference_row,
                message=(
                    "K.01 TB check 存在超过 SAD 的差异，底稿已有 Notes，"
                    f"最大差异={max_diff}，SAD={sad}"
                ),
                suggestion="请质检人员复核 Notes 是否说明差异原因、处理结论及是否需要进一步审计程序。",
            )
        ]

    return [
        _issue(
            rollforward=rollforward,
            severity=Severity.FAIL,
            field="tb_notes_text",
            source_row=rollforward.tb_difference_row,
            message=(
                "K.01 TB check 存在超过 SAD 的差异，但未读取到 Notes 解释，"
                f"最大差异={max_diff}，SAD={sad}"
            ),
            suggestion="请在 K.01 补充差异调查说明，至少说明差异原因、处理结论，以及是否需要进一步审计程序。",
        )
    ]
