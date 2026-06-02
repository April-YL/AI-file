from __future__ import annotations

from decimal import Decimal

from ingest.reconciliation import ReconciliationCheck, ReconciliationStatus
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.models import QcIssue, Severity

RULE_ID = "rollforward_fa_list_reconciliation"

_AMOUNT_TOL = Decimal("0.01")

_FIELD_BY_LINK_ID: dict[str, str] = {
    "fa_list_rollforward_net": "net_value",
    "fa_list_rollforward_original": "original_value",
    "fa_list_rollforward_accum_dep": "accumulated_depreciation",
}

_FIELD_LABELS: dict[str, str] = {
    "net_value": "净值",
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧",
}


def _rf_source_sheet(rollforward: RollforwardSheetDataset | None) -> str:
    if rollforward and rollforward.source_sheet:
        return rollforward.source_sheet
    return "K.01 Agree SL to GL"


def _issue(
    *,
    rollforward: RollforwardSheetDataset | None,
    field: str | None,
    severity: Severity,
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
        source_sheet=_rf_source_sheet(rollforward),
        source_row=source_row,
    )


def _check_table3(rollforward: RollforwardSheetDataset) -> list[QcIssue] | None:
    """主检查：读取 K.01 表3 check 结果。

    返回 None 表示表3不可读，调用方再走辅助/兜底逻辑。
    """
    if not rollforward.section_presence.get("b4_table3_check_with_table1"):
        return None

    values = list(rollforward.table3_check_values or [])
    if not values:
        return None

    diffs = [v for v in values if abs(v) > _AMOUNT_TOL]
    if not diffs:
        return []

    return [
        _issue(
            rollforward=rollforward,
            field="table3_check_with_table1",
            severity=Severity.WARN,
            message=(
                "K.01 表3（FA list 汇总表与后推明细表 check）存在非零差异："
                + "、".join(str(v) for v in diffs[:6])
            ),
            suggestion="请优先检查 K.01 表3 的 check 公式、表2 SUMIF 来源和表1后推金额；如差异超过 SAD，应记录调查结论。",
            source_row=rollforward.table3_check_row,
        )
    ]


def _fallback_issue_from_reconciliations(
    reconciliations: list[ReconciliationCheck] | None,
    *,
    rollforward: RollforwardSheetDataset | None,
) -> QcIssue | None:
    """兜底提示：表2/表3读不到时，才引用 Agent 自算合计。"""
    if not reconciliations:
        return None

    relevant = [
        c
        for c in reconciliations
        if c.link_id in _FIELD_BY_LINK_ID
        and c.status
        in (
            ReconciliationStatus.MISMATCH,
            ReconciliationStatus.MISSING_LEFT,
            ReconciliationStatus.MISSING_RIGHT,
            ReconciliationStatus.NEED_REVIEW,
        )
    ]
    if not relevant:
        return None

    parts: list[str] = []
    for check in relevant[:3]:
        field = _FIELD_BY_LINK_ID.get(check.link_id, check.link_id)
        label = _FIELD_LABELS.get(field, field)
        if check.status == ReconciliationStatus.MISMATCH:
            parts.append(
                f"{label}自算差异={check.difference}（FA list={check.left_value}，K.01={check.right_value}）"
            )
        else:
            parts.append(f"{label}无法自算核对：{check.message}")

    return _issue(
        rollforward=rollforward,
        field="fa_list_rollforward_fallback",
        severity=Severity.NEED_REVIEW,
        message=(
            "未能可靠读取 K.01 表3 check 结果；"
            "以下仅为 Agent 根据 FA list 与 K.01 合计做的兜底提示："
            + "；".join(parts)
        ),
        suggestion="请以 K.01 表2 SUMIF 汇总和表3 check 结果为准，人工确认底稿是否已完成 GL-002 核对。",
        source_row=(rollforward.total_row or rollforward.header_row) if rollforward else None,
    )


def check_rollforward_fa_list_reconciliation(
    reconciliations: list[ReconciliationCheck] | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
) -> list[QcIssue]:
    """GL-002：K.01 表3 check 为主，表2为辅助，Agent 自算仅兜底。"""
    if rollforward is None or not rollforward.source_sheet:
        return []

    table3_issues = _check_table3(rollforward)
    if table3_issues is not None:
        return table3_issues

    issues: list[QcIssue] = []
    if not rollforward.section_presence.get("b3_table2_fa_summary"):
        issues.append(
            _issue(
                rollforward=rollforward,
                field="b3_table2_fa_summary",
                severity=Severity.NEED_REVIEW,
                message="未可靠识别 K.01 表2（FA list 关键数据 SUMIF 汇总）",
                suggestion="请人工确认 K.01 是否保留表2，并检查表2是否从 FA list 正确汇总。",
                source_row=None,
            )
        )
    elif rollforward.table2_amount_count <= 0:
        issues.append(
            _issue(
                rollforward=rollforward,
                field="b3_table2_fa_summary",
                severity=Severity.NEED_REVIEW,
                message="已识别 K.01 表2，但未读取到可用于核对的汇总金额",
                suggestion="请检查表2 SUMIF 公式是否有结果，或确认读取范围是否覆盖表2。",
                source_row=rollforward.section_regions.get("b3_table2_fa_summary").anchor_row
                if rollforward.section_regions.get("b3_table2_fa_summary")
                else None,
            )
        )

    issues.append(
        _issue(
            rollforward=rollforward,
            field="b4_table3_check_with_table1",
            severity=Severity.NEED_REVIEW,
            message="未可靠读取 K.01 表3（FA list 汇总表与后推明细表 check）结果",
            suggestion="请人工查看表3 check 是否为 0/一致；后续可根据实际模板继续增强表3读取。",
            source_row=rollforward.section_regions.get("b4_table3_check_with_table1").anchor_row
            if rollforward.section_regions.get("b4_table3_check_with_table1")
            else None,
        )
    )

    fallback = _fallback_issue_from_reconciliations(
        reconciliations,
        rollforward=rollforward,
    )
    if fallback is not None:
        issues.append(fallback)
    return issues
