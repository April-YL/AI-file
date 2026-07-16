from __future__ import annotations

from decimal import Decimal

from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalReconciliationCell,
    DisposalReconciliationMatrix,
    DisposalReconciliationRow,
    DisposalTestSheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import DisposalListSummary
from ingest.models import AmountGroupStatus
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.execution_recorder import RuleExecutionRecorder
from rules.lead_common import field_values
from rules.models import ColumnContext, QcIssue, Severity
from rules.readiness import evaluate_rule_readiness, readiness_spec_from_registry
from rules.registry import get_by_rule_id
from rules.parsing import amount_tolerance, parse_amount

RULE_IDS = (
    "disposal_reconciliation_readability",
    "disposal_reconciliation_formula_source",
    "disposal_net_value_recalculation",
    "disposal_rollforward_reconciliation",
    "disposal_difference_investigation",
)
_MEASURES = ("original_value", "accumulated_depreciation", "impairment_provision", "net_value")
_MEASURE_LABELS = {
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧",
    "impairment_provision": "减值准备",
    "net_value": "计算净值",
}


def run_disposal_reconciliation_rules(
    *,
    disposal_list_summary: DisposalListSummary | None,
    disposal_test: DisposalTestSheetDataset | None,
    disposal_execution_path: DisposalExecutionPathDataset | None,
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
    readiness_ctx: ColumnContext | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    if _is_waived(disposal_execution_path):
        for rule_id in RULE_IDS:
            recorder.record_not_applicable(rule_id, "处置测试已豁免或注明不执行")
        return []
    issues = recorder.execute_rule(
        "disposal_reconciliation_readability",
        check_disposal_reconciliation_readability,
        disposal_test,
    )
    matrix = disposal_test.reconciliation_matrix if disposal_test else None
    if matrix is None or not matrix.usable_for_rules:
        for rule_id in (
            "disposal_reconciliation_formula_source",
            "disposal_net_value_recalculation",
            "disposal_rollforward_reconciliation",
            "disposal_difference_investigation",
        ):
            recorder.record_data_insufficient(rule_id, "处置总体核对矩阵未达到确定性规则执行条件")
        return issues
    issues.extend(
        recorder.execute_rule(
            "disposal_reconciliation_formula_source",
            check_disposal_reconciliation_formula_source,
            matrix,
            disposal_test.source_sheet,
        )
    )
    issues.extend(
        recorder.execute_rule(
            "disposal_net_value_recalculation",
            check_disposal_matrix_net_values,
            matrix,
            disposal_test.source_sheet,
        )
    )
    spec = get_by_rule_id("disposal_rollforward_reconciliation")
    decision = (
        evaluate_rule_readiness(readiness_spec_from_registry(spec), readiness_ctx)
        if spec is not None and readiness_ctx is not None
        else None
    )
    if readiness_ctx is None or (decision is not None and decision.ready):
        issues.extend(
            recorder.execute_rule(
                "disposal_rollforward_reconciliation",
                check_disposal_rollforward_reconciliation,
                disposal_list_summary=disposal_list_summary,
                matrix=matrix,
                source_sheet=disposal_test.source_sheet,
                rollforward=rollforward,
                lead=lead,
            )
        )
    else:
        recorder.record_data_insufficient(
            "disposal_rollforward_reconciliation",
            decision.note() if decision is not None else "rule readiness is unavailable",
        )
    issues.extend(
        recorder.execute_rule(
            "disposal_difference_investigation",
            check_disposal_difference_investigation,
            matrix,
            disposal_test.source_sheet,
            lead,
        )
    )
    return issues

def check_disposal_reconciliation_readability(
    disposal_test: DisposalTestSheetDataset | None,
) -> list[QcIssue]:
    if disposal_test is None:
        return [
            _issue(
                "disposal_reconciliation_readability",
                "reconciliation_matrix",
                Severity.NEED_REVIEW,
                "未读取到 K.02.2 处置测试页，无法执行处置总体金额勾稽。",
                "确认处置测试执行路径及 K.02.2 sheet 识别结果。",
                "K.02.2 处置测试",
            )
        ]
    matrix = disposal_test.reconciliation_matrix
    if matrix and matrix.usable_for_rules:
        return []
    detail = ""
    if matrix:
        detail = (
            f" 识别置信度={matrix.recognition_confidence}；"
            f"缺失={','.join(matrix.missing_components) or '无'}；"
            f"候选冲突={','.join(matrix.ambiguous_candidates) or '无'}。"
        )
    return [
        _issue(
            "disposal_reconciliation_readability",
            "reconciliation_matrix",
            Severity.NEED_REVIEW,
            "K.02.2 总体核对模块未达到确定性规则执行条件。" + detail,
            "人工确认总体核对模块、金额维度及处置清单/K.01 公式来源后再判断勾稽结果。",
            disposal_test.source_sheet,
            _matrix_anchor_row(matrix),
        )
    ]


def check_disposal_reconciliation_formula_source(
    matrix: DisposalReconciliationMatrix,
    source_sheet: str,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    for row_key, expected, label in (
        ("disposal_list", "处置清单", "处置/报废总金额"),
        ("rollforward", "k.01", "Breakdown 中处置/报废金额"),
    ):
        row = matrix.rows.get(row_key)
        formulas = [cell.formula for cell in row.measures.values() if cell.formula] if row else []
        if not formulas:
            issues.append(
                _issue(
                    "disposal_reconciliation_formula_source",
                    row_key,
                    Severity.NEED_REVIEW,
                    f"{label}未读取到公式，无法确认金额来源。",
                    f"人工确认该行是否直接或间接引用{expected}。",
                    source_sheet,
                    row.source_row if row else None,
                )
            )
        elif not any(expected in formula.lower() for formula in formulas):
            issues.append(
                _issue(
                    "disposal_reconciliation_formula_source",
                    row_key,
                    Severity.FAIL,
                    f"{label}公式未引用预期来源 {expected}。",
                    "修正公式来源，并重新核对总体金额。",
                    source_sheet,
                    row.source_row if row else None,
                )
            )
    return issues


def check_disposal_matrix_net_values(
    matrix: DisposalReconciliationMatrix,
    source_sheet: str,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    for row_key in ("disposal_list", "rollforward", "difference"):
        row = matrix.rows.get(row_key)
        if row is None:
            continue
        amounts = {key: _cell_amount(row.measures.get(key)) for key in _MEASURES}
        if all(amounts[key] is not None for key in _MEASURES):
            expected = amounts["original_value"] - amounts["accumulated_depreciation"] - amounts["impairment_provision"]
            diff = abs(amounts["net_value"] - expected)
            if diff > amount_tolerance(max(abs(amounts["net_value"]), abs(expected))):
                issues.append(
                    _issue(
                        "disposal_net_value_recalculation",
                        f"{row_key}.net_value",
                        Severity.FAIL,
                        f"{row.label}净值计算不成立：净值={amounts['net_value']}，按原值-累计折旧-减值准备计算={expected}。",
                        "检查 K.02.2 总体核对模块的金额或净值公式。",
                        source_sheet,
                        row.source_row,
                    )
                )
    return issues


def check_disposal_rollforward_reconciliation(
    *,
    disposal_list_summary: DisposalListSummary | None,
    matrix: DisposalReconciliationMatrix,
    source_sheet: str,
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    list_totals = _sale_scrap_totals(disposal_list_summary)
    matrix_list = matrix.rows.get("disposal_list")
    matrix_rollforward = matrix.rows.get("rollforward")
    sad = _lead_amount(lead, "sad")

    if disposal_list_summary is None:
        return [
            _issue(
                "disposal_rollforward_reconciliation",
                "disposal_list",
                Severity.NEED_REVIEW,
                "未读取到处置清单汇总，无法与 K.02.2 和 K.01 进行总体金额勾稽。",
                "确认处置清单识别及出售/报废减少方式分类。",
                source_sheet,
            )
        ]
    if disposal_list_summary.amount_group_status not in {None, AmountGroupStatus.CONFIRMED}:
        return [
            _issue(
                "disposal_rollforward_reconciliation",
                "amount_group",
                Severity.NEED_REVIEW,
                "处置清单金额组尚未确认，不能据其汇总金额执行总体勾稽。",
                "先确认同期间、同币种、同处置口径的完整金额组，再与 K.02.2 和 K.01 比较。",
                source_sheet,
            )
        ]

    component_details: list[str] = []
    net_details: list[str] = []
    over_sad_amounts: list[Decimal] = []
    source_row: int | None = None
    for measure in _MEASURES:
        list_amount = list_totals.get(measure)
        test_amount = _row_amount(matrix_list, measure)
        bkd_amount = _row_amount(matrix_rollforward, measure)
        direct_k01, direct_row = _rollforward_amount(rollforward, measure)
        comparisons = (
            ("处置清单汇总", list_amount, "K.02.2 处置/报废总金额", test_amount),
            ("K.02.2 处置/报废总金额", test_amount, "K.02.2 Breakdown", bkd_amount),
            ("K.02.2 Breakdown", bkd_amount, "K.01 后推处置行", direct_k01),
        )
        for left_label, left, right_label, right in comparisons:
            if left is None or right is None:
                continue
            diff = abs(abs(left) - abs(right))
            if diff <= amount_tolerance(max(abs(left), abs(right))):
                continue
            over_sad = sad is not None and diff > sad
            detail = (
                f"{_MEASURE_LABELS[measure]}：{left_label}={left}，"
                f"{right_label}={right}，差异={diff}"
            )
            if over_sad:
                over_sad_amounts.append(diff)
                detail += f"，超过 SAD（{sad}）"
            if source_row is None:
                source_row = direct_row or (matrix_rollforward.source_row if matrix_rollforward else None)
            if measure == "net_value":
                net_details.append(detail)
            else:
                component_details.append(detail)

    details = list(component_details)
    if net_details:
        if component_details:
            details.append("并导致净值差异：" + "；".join(net_details))
        else:
            details.extend(net_details)
    if not details:
        return []

    max_over_sad = max(over_sad_amounts) if over_sad_amounts else None
    message = "处置总体勾稽不一致：" + "；".join(details) + "。"
    if max_over_sad is not None:
        message += f" 最大差异超过 SAD（{sad}）。"
    return [
        _issue(
            "disposal_rollforward_reconciliation",
            "reconciliation_matrix",
            Severity.WARN,
            message,
            "核对出售/报废总体口径、处置清单明细、K.02.2 Breakdown 及 K.01 后推处置行。",
            source_sheet,
            source_row,
        )
    ]


def check_disposal_difference_investigation(
    matrix: DisposalReconciliationMatrix,
    source_sheet: str,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    sad = _lead_amount(lead, "sad")
    difference = matrix.rows.get("difference")
    investigation = matrix.rows.get("investigation")
    if sad is None or difference is None:
        return []
    issues: list[QcIssue] = []
    for measure in _MEASURES:
        amount = _row_amount(difference, measure)
        if amount is None or abs(amount) <= sad:
            continue
        answer = _cell_text(investigation.measures.get(measure)) if investigation else None
        if answer and _is_yes(answer):
            continue
        issues.append(
            _issue(
                "disposal_difference_investigation",
                measure,
                Severity.FAIL,
                f"处置{_MEASURE_LABELS[measure]}差异 {abs(amount)} 超过 SAD（{sad}），但未标记需要进一步调查。",
                "将该金额维度标记为需要调查，并记录调查过程和结论。",
                source_sheet,
                investigation.source_row if investigation else difference.source_row,
            )
        )
    return issues


def _sale_scrap_totals(summary: DisposalListSummary | None) -> dict[str, Decimal | None]:
    totals = {measure: Decimal("0") for measure in _MEASURES}
    if summary is None:
        return {measure: None for measure in _MEASURES}
    included = [bucket for bucket in summary.buckets if bucket.bucket_key in {"sale", "scrap", "sale_scrap"}]
    for bucket in included:
        totals["original_value"] += parse_amount(bucket.original_value_total) or Decimal("0")
        totals["accumulated_depreciation"] += parse_amount(bucket.accumulated_depreciation_total) or Decimal("0")
        totals["impairment_provision"] += parse_amount(bucket.impairment_provision_total) or Decimal("0")
    totals["net_value"] = (
        totals["original_value"]
        - abs(totals["accumulated_depreciation"])
        - abs(totals["impairment_provision"])
    )
    return totals


def _rollforward_amount(
    rollforward: RollforwardSheetDataset | None,
    measure: str,
) -> tuple[Decimal | None, int | None]:
    if measure == "net_value":
        original, row = get_movement_transaction_amount(rollforward, transaction_key="disposal", measure="original_value")
        accumulated, _ = get_movement_transaction_amount(
            rollforward, transaction_key="disposal", measure="accumulated_depreciation"
        )
        impairment, _ = get_movement_transaction_amount(
            rollforward, transaction_key="disposal", measure="impairment_provision"
        )
        if original is None or accumulated is None or impairment is None:
            return None, row
        return original - accumulated - impairment, row
    return get_movement_transaction_amount(rollforward, transaction_key="disposal", measure=measure)


def _lead_amount(lead: LeadSheetDataset | None, key: str) -> Decimal | None:
    if lead is None:
        return None
    amount = parse_amount(field_values(lead).get(key))
    return amount if amount is not None and amount > 0 else None


def _row_amount(row: DisposalReconciliationRow | None, measure: str) -> Decimal | None:
    return _cell_amount(row.measures.get(measure)) if row else None


def _cell_amount(cell: DisposalReconciliationCell | None) -> Decimal | None:
    return parse_amount(cell.value if cell else None)


def _cell_text(cell: DisposalReconciliationCell | None) -> str | None:
    return cell.value.strip() if cell and cell.value else None


def _matrix_anchor_row(matrix: DisposalReconciliationMatrix | None) -> int | None:
    if matrix is None:
        return None
    if matrix.header_row:
        return matrix.header_row
    first_row = next(iter(matrix.rows.values()), None)
    return first_row.source_row if first_row else None


def _is_yes(value: str) -> bool:
    text = value.strip().lower()
    return text in {"是", "yes", "y", "需要", "需调查"} or "是" in text


def _is_waived(path: DisposalExecutionPathDataset | None) -> bool:
    return path is not None and path.path_kind in {"summary_waived", "test_sheet_waiver_note"}


def _issue(
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    source_sheet: str,
    source_row: int | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=rule_id,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.02.2",
        source_sheet=source_sheet,
        source_row=source_row,
    )
