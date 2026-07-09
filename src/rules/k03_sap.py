from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from ingest.k03_sheet import (
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_TOD_SAMPLING,
    K03SheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.k03_observations import build_k03_not_applicable_observation
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount

RULE_IDS: tuple[str, ...] = (
    "sap_precision_selection",
    "sap_depreciation_difference",
)


def run_k03_sap_rules(
    dataset: K03SheetDataset,
    *,
    lead: LeadSheetDataset | None = None,
    k03_sheets: list[K03SheetDataset] | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    if dataset.execution_path not in {EXECUTION_PATH_SAP_MEDIUM, EXECUTION_PATH_SAP_HIGH}:
        note = "当前 K.03 工作表不是 SAP 折旧测试执行路径"
        for rule_id in RULE_IDS:
            recorder.record_not_applicable(rule_id, note)
            recorder.record_observation(
                rule_id,
                build_k03_not_applicable_observation(rule_id, dataset, reason=note),
            )
        return []

    issues: list[QcIssue] = []
    issues.extend(_check_precision_selection(dataset, lead=lead, k03_sheets=k03_sheets or []))
    issues.extend(_check_depreciation_difference(dataset))
    _record_execution(recorder, dataset, issues, lead=lead, k03_sheets=k03_sheets or [])
    return issues


def _check_precision_selection(
    dataset: K03SheetDataset,
    *,
    lead: LeadSheetDataset | None,
    k03_sheets: list[K03SheetDataset],
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    summary = dataset.summary
    sap_cra = str(summary.get("sap_cra") or "").strip()
    lead_values = field_values(lead) if lead is not None else {}
    lead_cra = str(lead_values.get("cra") or "").strip()
    sap_te = parse_amount(summary.get("sap_te"))
    lead_te = parse_amount(lead_values.get("te"))

    if not sap_cra:
        issues.append(
            _issue(
                dataset,
                "sap_precision_selection",
                "sap_cra",
                Severity.NEED_REVIEW,
                "K.03.1 SAP 折旧测试未能读取 CRA，无法判断中精度/高精度策略是否匹配风险等级。",
                "请确认 SAP 测试页 CRA 是否已从 Lead 正确链接，或在底稿中补充风险等级依据。",
                source_row=_summary_row(summary, "sap_cra"),
            )
        )
    elif lead_cra and _norm(sap_cra) != _norm(lead_cra):
        issues.append(
            _issue(
                dataset,
                "sap_precision_selection",
                "sap_cra",
                Severity.NEED_REVIEW,
                f"K.03.1 SAP 测试页 CRA 与 Lead 不一致：SAP={sap_cra}，Lead={lead_cra}。",
                "请核对 K.03.1 的 CRA 链接是否取自 K.00 Lead，并确认折旧测试策略是否仍适用。",
                source_row=_summary_row(summary, "sap_cra"),
            )
        )

    if sap_te is not None and lead_te is not None:
        tolerance = max(abs(lead_te), Decimal("1")) * Decimal("0.0001")
        if abs(sap_te - lead_te) > tolerance:
            issues.append(
                _issue(
                    dataset,
                    "sap_precision_selection",
                    "sap_te",
                    Severity.FAIL,
                    f"K.03.1 SAP 测试页 TE 与 Lead 不一致：SAP={sap_te}，Lead={lead_te}。",
                    "请修正 K.03.1 可容忍误差链接，确保折旧测试阈值使用 Lead 中的 TE。",
                    source_row=_summary_row(summary, "sap_te"),
                )
            )

    if dataset.execution_path == EXECUTION_PATH_SAP_MEDIUM and not _is_minimal_cra(sap_cra):
        has_tod_sampling = any(item.execution_path == EXECUTION_PATH_TOD_SAMPLING for item in k03_sheets)
        if not has_tod_sampling:
            issues.append(
                _issue(
                    dataset,
                    "sap_precision_selection",
                    "execution_path",
                    Severity.NEED_REVIEW,
                    "K.03.1 使用中精度 SAP，但当前 CRA 不是 Minimal，且未识别到 TOD 抽样补充测试。",
                    "请确认是否应改用高精度 SAP，或补充 TOD 抽样程序以取得足够保证。",
                )
            )
    return issues


def _check_depreciation_difference(dataset: K03SheetDataset) -> list[QcIssue]:
    summary = dataset.summary
    issues: list[QcIssue] = []
    if not summary.get("sap_expectation_text"):
        issues.append(
            _issue(
                dataset,
                "sap_depreciation_difference",
                "sap_expectation_text",
                Severity.NEED_REVIEW,
                "K.03.1 SAP 折旧测试未识别到预期构建说明。",
                "请在 SAP 测试页保留预期构建、细分基础和计算逻辑说明，便于复核人判断预期是否合理。",
            )
        )
    if not summary.get("sap_deviation_rows"):
        issues.append(
            _issue(
                dataset,
                "sap_depreciation_difference",
                "sap_deviation_rows",
                Severity.NEED_REVIEW,
                "K.03.1 SAP 折旧测试未识别到偏差阈值/偏差是否超过阈值的测试结果。",
                "请确认 SAP 测试表是否包含实际折旧、预期折旧、偏差、偏差阈值和超阈值判断。",
            )
        )
        return issues

    over_count = int(summary.get("sap_deviation_over_threshold_count") or 0)
    if over_count and not (summary.get("sap_note_text") or summary.get("sap_conclusion_text")):
        issues.append(
            _issue(
                dataset,
                "sap_depreciation_difference",
                "sap_deviation_over_threshold",
                Severity.FAIL,
                f"K.03.1 SAP 折旧测试存在 {over_count} 项偏差超过阈值，但未识别到差异说明或结论。",
                "请针对超过阈值的折旧偏差补充原因分析、后续处理和总体结论。",
            )
        )
    elif over_count:
        issues.append(
            _issue(
                dataset,
                "sap_depreciation_difference",
                "sap_deviation_over_threshold",
                Severity.NEED_REVIEW,
                f"K.03.1 SAP 折旧测试存在 {over_count} 项偏差超过阈值，底稿已有说明或结论，需要复核充分性。",
                "请复核差异说明是否覆盖所有超阈值项目，并判断是否需要调整或扩大测试。",
            )
        )
    return issues


def _record_execution(
    recorder: RuleExecutionRecorder,
    dataset: K03SheetDataset,
    issues: Iterable[QcIssue],
    *,
    lead: LeadSheetDataset | None,
    k03_sheets: list[K03SheetDataset],
) -> None:
    issue_list = list(issues)
    for rule_id in RULE_IDS:
        count = sum(1 for issue in issue_list if issue.rule_id == rule_id)
        recorder.record_executed(
            rule_id,
            count,
            observation=_sap_observation(rule_id, dataset, issue_list, lead=lead, k03_sheets=k03_sheets),
        )


def _sap_observation(
    rule_id: str,
    dataset: K03SheetDataset,
    issues: list[QcIssue],
    *,
    lead: LeadSheetDataset | None,
    k03_sheets: list[K03SheetDataset],
) -> dict[str, Any]:
    summary = dataset.summary
    values = [
        _value("执行路径", dataset.execution_path, None, None, "execution_path"),
        _value("SAP CRA", summary.get("sap_cra"), _summary_row(summary, "sap_cra"), _summary_col(summary, "sap_cra"), "risk_level"),
        _value("SAP TE", summary.get("sap_te"), _summary_row(summary, "sap_te"), _summary_col(summary, "sap_te"), "materiality_amount"),
        _value("SAP 偏差超阈值数量", summary.get("sap_deviation_over_threshold_count"), None, None, "test_result"),
    ]
    if lead is not None:
        lead_values = field_values(lead)
        values.extend(
            [
                _value("Lead CRA", lead_values.get("cra"), None, None, "risk_level"),
                _value("Lead TE", lead_values.get("te"), None, None, "materiality_amount"),
            ]
        )
    missing: list[str] = []
    if rule_id == "sap_precision_selection":
        if not summary.get("sap_cra"):
            missing.append("K.03.1 SAP CRA")
        if not summary.get("sap_te"):
            missing.append("K.03.1 SAP TE")
        if dataset.execution_path == EXECUTION_PATH_SAP_MEDIUM:
            has_tod = any(item.execution_path == EXECUTION_PATH_TOD_SAMPLING for item in k03_sheets)
            values.append(_value("是否识别 TOD 抽样补充", has_tod, None, None, "execution_path"))
    else:
        if not summary.get("sap_expectation_text"):
            missing.append("SAP 预期构建说明")
        if not summary.get("sap_deviation_rows"):
            missing.append("SAP 偏差测试结果")

    return _observation(
        dataset,
        section="K.03.1 SAP 折旧测试",
        key_columns=["sap_cra", "sap_te", "sap_deviation_rows"],
        values_read=values,
        missing_data=missing,
        logic=(
            "系统读取 K.03.1 SAP 测试页的执行路径、CRA、TE、偏差阈值判断和说明区，"
            "判断折旧测试策略及偏差处理是否需要复核。"
        ),
        expected="SAP 测试页应使用与 Lead 一致的 CRA/TE，并保留预期、阈值、偏差判断和必要说明。",
        actual=f"本次识别执行路径={dataset.execution_path}，finding 数={sum(1 for item in issues if item.rule_id == rule_id)}。",
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
    rows = [row for row in (_summary_row(dataset.summary, "sap_cra"), _summary_row(dataset.summary, "sap_te")) if row]
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


def _summary_row(summary: dict[str, Any], key: str) -> int | None:
    row = summary.get(f"{key}_row")
    return row if isinstance(row, int) else None


def _summary_col(summary: dict[str, Any], key: str) -> int | None:
    col = summary.get(f"{key}_col")
    return col if isinstance(col, int) else None


def _is_minimal_cra(value: str) -> bool:
    return _norm(value) in {"minimal", "最低", "最小", "极低"}


def _norm(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").lower()


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
        procedure_code="K.03.1",
        source_sheet=dataset.sheet_name,
        source_row=source_row,
    )
