from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from ingest.k03_sheet import EXECUTION_PATH_TOD_SAMPLING, K03SheetDataset
from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.execution_recorder import RuleExecutionRecorder
from rules.k03_observations import build_k03_not_applicable_observation
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import amount_tolerance, parse_amount

RULE_IDS: tuple[str, ...] = (
    "depreciation_tod_sampling",
    "depreciation_tod_difference",
)


def run_k03_tod_sampling_rules(
    dataset: K03SheetDataset | None,
    *,
    sample_output: K03SheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    if dataset is None:
        note = "未识别到 K.03.2 TOD 抽样主测试页"
        for rule_id in RULE_IDS:
            recorder.record_data_insufficient(rule_id, note)
        return []
    if dataset.execution_path != EXECUTION_PATH_TOD_SAMPLING or dataset.template_type != "tod_sampling":
        note = "当前 K.03 工作表不是 TOD 抽样主测试页"
        for rule_id in RULE_IDS:
            recorder.record_not_applicable(rule_id, note)
            recorder.record_observation(
                rule_id,
                build_k03_not_applicable_observation(rule_id, dataset, reason=note),
            )
        return []

    issues: list[QcIssue] = []
    issues.extend(_check_sampling_process(dataset, sample_output=sample_output, lead=lead, rollforward=rollforward))
    issues.extend(_check_sample_difference(dataset))
    _record_execution(recorder, dataset, issues, sample_output=sample_output, lead=lead, rollforward=rollforward)
    return issues


def _check_sampling_process(
    dataset: K03SheetDataset,
    *,
    sample_output: K03SheetDataset | None,
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    summary = dataset.summary
    if sample_output is None:
        issues.append(
            _issue(
                dataset,
                "depreciation_tod_sampling",
                "sample_output",
                Severity.NEED_REVIEW,
                "K.03.2 TOD 抽样测试未识别到 K.03.2a 折旧选样输出。",
                "请确认底稿中是否保留选样输出页，以便复核抽样参数、关键项目和样本生成过程。",
            )
        )
    else:
        output_summary = sample_output.summary
        _check_sample_output_params(dataset, sample_output, output_summary, issues, lead=lead)

    population = parse_amount(summary.get("tod_population_amount"))
    rf_amount, rf_row = get_movement_transaction_amount(
        rollforward,
        transaction_key="depreciation",
        measure="accumulated_depreciation",
    )
    if rf_amount is None and rollforward is not None:
        rf_amount = rollforward.table4_rollforward_depreciation
        rf_row = rollforward.table4_rollforward_depreciation_row
    if population is None:
        issues.append(
            _issue(
                dataset,
                "depreciation_tod_sampling",
                "tod_population_amount",
                Severity.NEED_REVIEW,
                "K.03.2 TOD 抽样未能读取折旧费用总体金额。",
                "请确认抽样总体金额是否已填写或链接至 K.01/Breakdown。",
            )
        )
    elif rf_amount is not None:
        diff = population - rf_amount
        threshold = _sad_or_small(lead, population, rf_amount)
        if abs(diff) > threshold:
            issues.append(
                _issue(
                    dataset,
                    "depreciation_tod_sampling",
                    "tod_population_amount",
                    Severity.NEED_REVIEW,
                    f"K.03.2 TOD 抽样总体与 K.01 折旧金额不一致：TOD={population}，K.01={rf_amount}，差异={diff}。",
                    "请核对 TOD 抽样总体是否与 K.01 本期计提折旧一致，或补充差异说明。",
                    source_row=rf_row,
                )
            )
    if not summary.get("tod_key_item_reason_text"):
        issues.append(
            _issue(
                dataset,
                "depreciation_tod_sampling",
                "tod_key_item_reason_text",
                Severity.NEED_REVIEW,
                "K.03.2 TOD 抽样未识别到关键项目选取依据说明。",
                "请补充关键项目筛选标准或说明无关键项目的判断依据。",
            )
        )
    return issues


def _check_sample_output_params(
    dataset: K03SheetDataset,
    sample_output: K03SheetDataset,
    summary: dict[str, Any],
    issues: list[QcIssue],
    *,
    lead: LeadSheetDataset | None,
) -> None:
    currency = str(summary.get("sample_output_sampling_currency") or "")
    if "本期计提折旧" not in currency and "depreciation" not in currency.lower():
        issues.append(
            _issue(
                sample_output,
                "depreciation_tod_sampling",
                "sample_output_sampling_currency",
                Severity.FAIL,
                f"K.03.2a 选样输出的抽样货币单元不是本期计提折旧：{currency or '未填写'}。",
                "请确认选样输出使用本期计提折旧作为抽样货币单元。",
            )
        )
    expected_flags = {
        "sample_output_dual_purpose": ("否", "no"),
        "sample_output_overstatement": ("是", "yes"),
    }
    for field, accepted in expected_flags.items():
        value = str(summary.get(field) or "").strip()
        if value and not any(token in value.lower() for token in accepted):
            issues.append(
                _issue(
                    sample_output,
                    "depreciation_tod_sampling",
                    field,
                    Severity.NEED_REVIEW,
                    f"K.03.2a 选样参数 {field} 与 SOP 预期不一致：{value}。",
                    "请复核抽样参数是否符合折旧 TOD 抽样程序设计。",
                )
            )
    method = str(summary.get("sample_output_sampling_method") or "")
    if method and "随机" not in method and "random" not in method.lower():
        issues.append(
            _issue(
                sample_output,
                "depreciation_tod_sampling",
                "sample_output_sampling_method",
                Severity.NEED_REVIEW,
                f"K.03.2a 选样方法不是随机抽样：{method}。",
                "请确认折旧 TOD 抽样是否应使用随机抽样，或补充替代方法依据。",
            )
        )

    lead_te = parse_amount(field_values(lead).get("te")) if lead is not None else None
    output_te = parse_amount(summary.get("sample_output_te"))
    if lead_te is not None and output_te is not None:
        tolerance = max(abs(lead_te), Decimal("1")) * Decimal("0.0001")
        if abs(lead_te - output_te) > tolerance:
            issues.append(
                _issue(
                    sample_output,
                    "depreciation_tod_sampling",
                    "sample_output_te",
                    Severity.FAIL,
                    f"K.03.2a 选样输出 TE 与 Lead 不一致：选样输出={output_te}，Lead={lead_te}。",
                    "请修正选样输出参数，确保抽样以 Lead 中 TE 为基础。",
                )
            )


def _check_sample_difference(dataset: K03SheetDataset) -> list[QcIssue]:
    summary = dataset.summary
    issues: list[QcIssue] = []
    if int(summary.get("tod_sample_rows_count") or 0) <= 0:
        issues.append(
            _issue(
                dataset,
                "depreciation_tod_difference",
                "tod_sample_rows",
                Severity.NEED_REVIEW,
                "K.03.2 TOD 抽样未识别到样本测试明细。",
                "请确认 TOD 抽样测试页是否列示样本、折旧重新计算所需字段和测试结果。",
            )
        )
    if not summary.get("tod_conclusion_text"):
        issues.append(
            _issue(
                dataset,
                "depreciation_tod_difference",
                "tod_conclusion_text",
                Severity.NEED_REVIEW,
                "K.03.2 TOD 抽样未识别到测试结论。",
                "请在 TOD 抽样测试页补充样本测试结果和总体结论。",
            )
        )
    return issues


def _record_execution(
    recorder: RuleExecutionRecorder,
    dataset: K03SheetDataset,
    issues: Iterable[QcIssue],
    *,
    sample_output: K03SheetDataset | None,
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> None:
    issue_list = list(issues)
    for rule_id in RULE_IDS:
        count = sum(1 for issue in issue_list if issue.rule_id == rule_id)
        recorder.record_executed(
            rule_id,
            count,
            observation=_tod_observation(
                rule_id,
                dataset,
                issue_list,
                sample_output=sample_output,
                lead=lead,
                rollforward=rollforward,
            ),
        )


def _tod_observation(
    rule_id: str,
    dataset: K03SheetDataset,
    issues: list[QcIssue],
    *,
    sample_output: K03SheetDataset | None,
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> dict[str, Any]:
    summary = dataset.summary
    values = [
        _value("TOD 抽样总体", summary.get("tod_population_amount"), None, None, "depreciation_amount"),
        _value("关键项目金额", summary.get("tod_key_item_amount"), None, None, "depreciation_amount"),
        _value("样本明细行数", summary.get("tod_sample_rows_count"), None, None, "sample_count"),
        _value("测试结论", summary.get("tod_conclusion_text"), None, None, "conclusion_text"),
    ]
    if sample_output is not None:
        output = sample_output.summary
        values.extend(
            [
                _value("选样输出 TE", output.get("sample_output_te"), None, None, "materiality_amount"),
                _value("抽样货币单元", output.get("sample_output_sampling_currency"), None, None, "sampling_parameter"),
                _value("抽样方法", output.get("sample_output_sampling_method"), None, None, "sampling_parameter"),
            ]
        )
    rf_amount, rf_row = get_movement_transaction_amount(
        rollforward,
        transaction_key="depreciation",
        measure="accumulated_depreciation",
    )
    if rf_amount is None and rollforward is not None:
        rf_amount = rollforward.table4_rollforward_depreciation
        rf_row = rollforward.table4_rollforward_depreciation_row
    if rf_amount is not None:
        values.append(_value("K.01 本期计提折旧", rf_amount, rf_row, None, "depreciation_amount"))
    if lead is not None:
        values.append(_value("Lead TE", field_values(lead).get("te"), None, None, "materiality_amount"))

    missing: list[str] = []
    if rule_id == "depreciation_tod_sampling":
        if sample_output is None:
            missing.append("K.03.2a 折旧选样输出")
        if not summary.get("tod_population_amount"):
            missing.append("TOD 抽样总体金额")
        if not summary.get("tod_key_item_reason_text"):
            missing.append("关键项目选取依据")
    else:
        if not summary.get("tod_sample_rows_count"):
            missing.append("TOD 样本测试明细")
        if not summary.get("tod_conclusion_text"):
            missing.append("TOD 抽样测试结论")

    return _observation(
        dataset,
        section="K.03.2 TOD 抽样折旧测试",
        key_columns=["tod_population_amount", "sample_output_sampling_currency", "tod_sample_rows_count"],
        values_read=values,
        missing_data=missing,
        logic="系统读取 TOD 抽样主测试页和 K.03.2a 选样输出，检查总体、关键项目、抽样参数、样本明细和结论。",
        expected="TOD 抽样应能追溯总体金额、关键项目依据、选样参数、样本测试明细和结论。",
        actual=f"本次识别主测试页={dataset.sheet_name}，选样输出={sample_output.sheet_name if sample_output else '未识别'}。",
        summary="触发 finding。" if any(item.rule_id == rule_id for item in issues) else "未触发 finding。",
    )


def _observation(
    dataset: K03SheetDataset,
    *,
    section: str,
    key_columns: list[str],
    values_read: list[dict[str, Any]],
    missing_data: list[str],
    logic: str,
    expected: str,
    actual: str,
    summary: str,
) -> dict[str, Any]:
    rows = dataset.header_rows[:3]
    return {
        "checked_data": [
            {
                "sheet": dataset.sheet_name,
                "section": section,
                "location": "行" + ", ".join(str(row) for row in rows) if rows else None,
                "identified_by": {
                    "sheet_name": dataset.sheet_name,
                    "section": section,
                    "matched_keywords": [dataset.sheet_name, dataset.execution_path],
                    "matched_rows": rows,
                    "matched_columns": [],
                },
                "key_columns": key_columns,
                "values_read": values_read,
                "missing_data": missing_data,
            }
        ],
        "check_logic": logic,
        "expected_result": expected,
        "actual_result": actual,
        "result_summary": summary,
    }


def _sad_or_small(lead: LeadSheetDataset | None, *amounts: Decimal) -> Decimal:
    sad = parse_amount(field_values(lead).get("sad")) if lead is not None else None
    if sad is not None and sad > 0:
        return sad
    base = max([abs(amount) for amount in amounts if amount is not None] or [Decimal("1")])
    return amount_tolerance(base, absolute=Decimal("0.01"))


def _value(label: str, value: Any, row: int | None, column: int | None, amount_type: str) -> dict[str, Any]:
    return {
        "label": label,
        "value": "" if value is None else str(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": None,
        "amount_type": amount_type,
    }


def _cell(row: int | None, column: int | None) -> str | None:
    if row is None or column is None:
        return None
    return f"{_column_letter(column)}{row}"


def _column_letter(column: int) -> str:
    letters = ""
    while column > 0:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _issue(
    dataset: K03SheetDataset,
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    *,
    source_row: int | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=rule_id,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.03.2",
        source_sheet=dataset.sheet_name,
        source_row=source_row,
    )
