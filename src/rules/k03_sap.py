from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from ingest.k03_sheet import (
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_TOD_BY_ITEM,
    EXECUTION_PATH_TOD_SAMPLING,
    K03ExecutionProfile,
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
    "sap_te_consistency",
    "sap_high_cra_consistency",
    "sap_depreciation_difference",
    "sap_medium_category_deviation_explanation",
    "sap_high_category_deviation_explanation",
)


def run_k03_sap_rules(
    dataset: K03SheetDataset,
    *,
    lead: LeadSheetDataset | None = None,
    k03_sheets: list[K03SheetDataset] | None = None,
    k03_execution_profile: K03ExecutionProfile | None = None,
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

    precision_issues, precision_ready = _check_precision_selection(
        dataset,
        profile=k03_execution_profile,
    )
    te_issues, te_ready = _check_te_consistency(dataset, lead=lead)
    high_cra_issues, high_cra_status = _check_high_cra_consistency(
        dataset,
        profile=k03_execution_profile,
    )
    difference_issues = _check_depreciation_difference(dataset)
    medium_issues, medium_ready = _check_category_deviation_explanation(
        dataset, rule_id="sap_medium_category_deviation_explanation", summary_key="sap_medium_deviation_items"
    )
    high_issues, high_ready = _check_category_deviation_explanation(
        dataset, rule_id="sap_high_category_deviation_explanation", summary_key="sap_high_deviation_items"
    )
    issues = [
        *precision_issues,
        *te_issues,
        *high_cra_issues,
        *difference_issues,
        *medium_issues,
        *high_issues,
    ]

    _record_rule_result(
        recorder,
        "sap_precision_selection",
        dataset,
        precision_issues,
        status="executed" if precision_ready else "data_insufficient",
        lead=lead,
        profile=k03_execution_profile,
    )
    _record_rule_result(
        recorder,
        "sap_te_consistency",
        dataset,
        te_issues,
        status="executed" if te_ready else "data_insufficient",
        lead=lead,
        profile=k03_execution_profile,
    )
    _record_rule_result(
        recorder,
        "sap_high_cra_consistency",
        dataset,
        high_cra_issues,
        status=high_cra_status,
        lead=lead,
        profile=k03_execution_profile,
    )
    _record_rule_result(
        recorder,
        "sap_depreciation_difference",
        dataset,
        difference_issues,
        status="executed",
        lead=lead,
        profile=k03_execution_profile,
    )
    _record_rule_result(
        recorder,
        "sap_medium_category_deviation_explanation",
        dataset,
        medium_issues,
        status=("executed" if medium_ready else "data_insufficient") if dataset.execution_path == EXECUTION_PATH_SAP_MEDIUM else "not_applicable",
        lead=lead,
        profile=k03_execution_profile,
    )
    _record_rule_result(
        recorder,
        "sap_high_category_deviation_explanation",
        dataset,
        high_issues,
        status=("executed" if high_ready else "data_insufficient") if dataset.execution_path == EXECUTION_PATH_SAP_HIGH else "not_applicable",
        lead=lead,
        profile=k03_execution_profile,
    )
    return issues


def _check_precision_selection(
    dataset: K03SheetDataset,
    *,
    profile: K03ExecutionProfile | None,
) -> tuple[list[QcIssue], bool]:
    lead_cra = _profile_cra(profile)
    if not lead_cra:
        return [], False
    if dataset.execution_path != EXECUTION_PATH_SAP_MEDIUM:
        return [], True
    if _is_minimal_cra(lead_cra) or _profile_has_tod(profile):
        return [], True
    return [
        _issue(
            dataset,
            "sap_precision_selection",
            "execution_path",
            Severity.NEED_REVIEW,
            f"K.03.1 使用中精度 SAP，Lead 计价/计量认定 CRA 为 {lead_cra}，且未识别到已执行的 TOD 补充测试。",
            "请确认是否应改用高精度 SAP，或补充 TOD 程序以取得充分、适当的审计证据。",
        )
    ], True


def _check_te_consistency(
    dataset: K03SheetDataset,
    *,
    lead: LeadSheetDataset | None,
) -> tuple[list[QcIssue], bool]:
    summary = dataset.summary
    sap_te = parse_amount(summary.get("sap_te"))
    lead_values = field_values(lead) if lead is not None else {}
    lead_te = parse_amount(lead_values.get("te"))
    if sap_te is None or lead_te is None:
        return [], False
    tolerance = max(abs(lead_te), Decimal("1")) * Decimal("0.0001")
    if abs(sap_te - lead_te) <= tolerance:
        return [], True
    return [
        _issue(
            dataset,
            "sap_te_consistency",
            "sap_te",
            Severity.FAIL,
            f"K.03.1 SAP 测试页 TE 与 Lead 不一致：SAP={sap_te}，Lead={lead_te}。",
            "请修正 K.03.1 可容忍误差链接，确保 SAP 使用 Lead 中的 TE。",
            source_row=_summary_row(summary, "sap_te"),
        )
    ], True


def _check_high_cra_consistency(
    dataset: K03SheetDataset,
    *,
    profile: K03ExecutionProfile | None,
) -> tuple[list[QcIssue], str]:
    if dataset.execution_path != EXECUTION_PATH_SAP_HIGH:
        return [], "not_applicable"
    sap_cra = str(dataset.summary.get("sap_cra") or "").strip()
    lead_cra = _profile_cra(profile)
    if not sap_cra or not lead_cra:
        return [], "data_insufficient"
    if _norm(sap_cra) == _norm(lead_cra):
        return [], "executed"
    return [
        _issue(
            dataset,
            "sap_high_cra_consistency",
            "sap_cra",
            Severity.FAIL,
            f"K.03.1 高精度 SAP 页 CRA 与 Lead 计价/计量认定 CRA 不一致：SAP={sap_cra}，Lead={lead_cra}。",
            "请核对高精度 SAP 页 CRA，并确保其与 K.00 Lead 的计价/计量认定一致。",
            source_row=_summary_row(dataset.summary, "sap_cra"),
        )
    ], "executed"


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
    if summary.get("sap_medium_deviation_items") or summary.get("sap_high_deviation_items"):
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
    return issues


def _check_category_deviation_explanation(
    dataset: K03SheetDataset,
    *,
    rule_id: str,
    summary_key: str,
) -> tuple[list[QcIssue], bool]:
    items = list(dataset.summary.get(summary_key) or [])
    if not items:
        return [], False
    issues: list[QcIssue] = []
    ready = True
    for item in items:
        category = str(item.get("asset_category") or "未识别类别")
        deviation = parse_amount(item.get("deviation_amount"))
        threshold = parse_amount(item.get("threshold"))
        if deviation is None or threshold is None:
            ready = False
            continue
        computed_over = abs(deviation) > abs(threshold)
        stated_text = str(item.get("over_threshold_stated") or "").strip()
        if not stated_text:
            ready = False
            continue
        stated_over = _looks_yes(stated_text)
        if stated_over != computed_over:
            issues.append(_issue(
                dataset, rule_id, f"{category}:over_threshold", Severity.NEED_REVIEW,
                f"{category} 的偏差金额与阈值比较结果，和底稿“是否超过阈值”标识不一致。",
                "请核对偏差、阈值及“是否超过阈值”公式或人工判断。",
                source_row=_item_source_row(item),
            ))
            continue
        if not computed_over:
            continue
        note = item.get("matched_note") or {}
        note_text = str(note.get("text") or "").strip()
        if not _has_substantive_note(note_text):
            issues.append(_issue(
                dataset, rule_id, f"{category}:explanation", Severity.FAIL,
                f"{category} 的折旧偏差超过阈值，但未识别到可追溯的对应说明。",
                "请在 Notes 中补充该类别（或合计）超阈值偏差的原因与后续处理说明，并建立明确索引。",
                source_row=_item_source_row(item),
            ))
        else:
            issues.append(_issue(
                dataset, rule_id, f"{category}:explanation", Severity.NEED_REVIEW,
                f"{category} 的折旧偏差超过阈值，已识别到对应说明，需人工复核说明是否充分。",
                "请复核该说明是否解释偏差原因、量化影响及是否需要调整或扩大测试。",
                source_row=_item_source_row(item),
            ))
    return issues, ready


def _item_source_row(item: dict[str, Any]) -> int | None:
    cell = str(item.get("deviation_cell") or "")
    match = re.search(r"(\d+)$", cell)
    return int(match.group(1)) if match else None


def _has_substantive_note(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text).lower()
    normalized = re.sub(r"^nb\d+[：:;；,，\-—]*", "", normalized)
    if not normalized:
        return False
    return normalized not in {"nb1", "nb2", "nb3", "tbd", "todo", "na", "n/a", "待补", "待说明", "-", "--"}


def _looks_yes(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"是", "yes", "y", "true"} or text.startswith("是")


def _record_rule_result(
    recorder: RuleExecutionRecorder,
    rule_id: str,
    dataset: K03SheetDataset,
    issues: Iterable[QcIssue],
    *,
    status: str,
    lead: LeadSheetDataset | None,
    profile: K03ExecutionProfile | None,
) -> None:
    issue_list = list(issues)
    observation = _sap_observation(
        rule_id,
        dataset,
        issue_list,
        lead=lead,
        profile=profile,
    )
    if status == "executed":
        recorder.record_executed(
            rule_id,
            sum(1 for issue in issue_list if issue.rule_id == rule_id),
            observation=observation,
        )
        return
    if status == "not_applicable":
        note = "当前 SAP 路径不适用该规则"
        recorder.record_not_applicable(rule_id, note)
        recorder.record_observation(rule_id, observation)
        return
    note = "执行该 SAP 规则所需资料未能可靠识别"
    recorder.record_data_insufficient(rule_id, note)
    recorder.record_observation(rule_id, observation)


def _sap_observation(
    rule_id: str,
    dataset: K03SheetDataset,
    issues: list[QcIssue],
    *,
    lead: LeadSheetDataset | None,
    profile: K03ExecutionProfile | None,
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
                _value("Lead TE", lead_values.get("te"), None, None, "materiality_amount"),
            ]
        )
    linkage = profile.lead_linkage if profile is not None else None
    values.extend(
        [
            _value(
                "Lead V/M CRA",
                linkage.cra if linkage else None,
                linkage.source_row if linkage else None,
                None,
                "risk_level",
            ),
            _value(
                "是否识别已执行 TOD 补充",
                _profile_has_tod(profile),
                None,
                None,
                "execution_path",
            ),
        ]
    )
    category_key = {
        "sap_medium_category_deviation_explanation": "sap_medium_deviation_items",
        "sap_high_category_deviation_explanation": "sap_high_deviation_items",
    }.get(rule_id)
    if category_key:
        category_items = summary.get(category_key) or []
        values.append(_value("已识别逐类别项目数", len(category_items), None, None, "count"))
        # Observation evidence is bounded by the recorder schema.  Findings
        # themselves retain every affected category and its cell anchor.
        for item in category_items[:2]:
            values.extend(
                [
                    _value("资产类别", item.get("asset_category"), _item_source_row(item), None, "asset_category"),
                    _value("偏差金额", item.get("deviation_amount"), _item_source_row(item), None, "amount"),
                    _value("偏差阈值", item.get("threshold"), _item_source_row(item), None, "amount"),
                    _value("底稿是否超过阈值", item.get("over_threshold_stated"), _item_source_row(item), None, "test_result"),
                    _value("Notes 匹配标记", item.get("note_reference") or (item.get("matched_note") or {}).get("marker"), _item_source_row(item), None, "note_reference"),
                ]
            )
    missing: list[str] = []
    if rule_id == "sap_precision_selection":
        if not _profile_cra(profile):
            missing.append("Lead 计价/计量认定 CRA")
    elif rule_id == "sap_te_consistency":
        if summary.get("sap_te") is None:
            missing.append("K.03.1 SAP TE")
        if lead is None or parse_amount(field_values(lead).get("te")) is None:
            missing.append("Lead TE")
    elif rule_id == "sap_high_cra_consistency":
        if dataset.execution_path != EXECUTION_PATH_SAP_HIGH:
            missing.append("仅高精度 SAP 适用")
        if not summary.get("sap_cra"):
            missing.append("高精度 SAP CRA")
        if not _profile_cra(profile):
            missing.append("Lead 计价/计量认定 CRA")
    else:
        if not summary.get("sap_expectation_text"):
            missing.append("SAP 预期构建说明")
        if not summary.get("sap_deviation_rows"):
            missing.append("SAP 偏差测试结果")
        if category_key and not summary.get(category_key):
            missing.append("SAP 逐类别偏差、阈值或说明索引")

    return _observation(
        dataset,
        section="K.03.1 SAP 折旧测试",
        key_columns=["sap_cra", "sap_te", "sap_deviation_rows"],
        values_read=values,
        missing_data=missing,
        logic=(
            "系统读取 K.03.1 SAP 路径和参数，并使用 K03 profile 已关联的 Lead 计价/计量 CRA，"
            "逐条检查策略选择、TE、高精度 CRA 或偏差处理；逐类别规则以偏差绝对值与底稿阈值比较，并核对对应 Notes。"
        ),
        expected="SAP 策略应匹配 Lead V/M CRA；TE 应与 Lead 一致；高精度页 CRA 应与 Lead V/M CRA 一致。",
        actual=f"本次识别执行路径={dataset.execution_path}，finding 数={sum(1 for item in issues if item.rule_id == rule_id)}。",
        summary="触发 finding。" if any(item.rule_id == rule_id for item in issues) else "未触发 finding。",
    )


def _profile_cra(profile: K03ExecutionProfile | None) -> str:
    if profile is None or profile.lead_linkage is None:
        return ""
    return str(profile.lead_linkage.cra or "").strip()


def _profile_has_tod(profile: K03ExecutionProfile | None) -> bool:
    if profile is None:
        return False
    return any(
        path in profile.executed_depreciation_paths
        for path in (EXECUTION_PATH_TOD_SAMPLING, EXECUTION_PATH_TOD_BY_ITEM)
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
