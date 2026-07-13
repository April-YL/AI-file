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
from rules.parsing import parse_amount

RULE_IDS: tuple[str, ...] = (
    "depreciation_tod_sampling",
    "depreciation_tod_difference",
    "k03_tod_sampling_output_required",
    "k03_tod_sampling_currency",
    "k03_tod_sampling_te_consistency",
    "k03_tod_sampling_population_reconciliation",
    "k03_tod_sampling_count_consistency",
    "k03_tod_sampling_identity_consistency",
    "k03_tod_sampling_attributes",
    "k03_tod_sampling_difference_followup",
    "k03_tod_sampling_documentation",
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
    statuses: dict[str, str] = {
        "depreciation_tod_sampling": "not_applicable",
        "depreciation_tod_difference": "not_applicable",
    }
    checks = (
        ("k03_tod_sampling_output_required", _check_output_required(dataset, sample_output)),
        ("k03_tod_sampling_currency", _check_currency(dataset, sample_output)),
        ("k03_tod_sampling_te_consistency", _check_te(dataset, sample_output, lead)),
        ("k03_tod_sampling_population_reconciliation", _check_population(dataset, lead, rollforward)),
        ("k03_tod_sampling_count_consistency", _check_counts(dataset, sample_output)),
        ("k03_tod_sampling_identity_consistency", _check_identities(dataset, sample_output)),
        ("k03_tod_sampling_attributes", _check_attributes(dataset)),
        ("k03_tod_sampling_difference_followup", _check_difference_followup(dataset)),
        ("k03_tod_sampling_documentation", _check_documentation(dataset)),
    )
    for rule_id, (rule_issues, status) in checks:
        issues.extend(rule_issues)
        statuses[rule_id] = status
    _record_results(
        recorder, dataset, issues, statuses,
        sample_output=sample_output, lead=lead, rollforward=rollforward,
    )
    return issues


def _check_output_required(dataset, output):
    if output is None:
        return [_issue(dataset, "k03_tod_sampling_output_required", "sample_output", Severity.NEED_REVIEW,
            "TOD 抽样未识别到配套选样输出。", "请确认是否保留可追溯的选样输出。")], "executed"
    state = output.summary.get("sample_output_detail_state")
    return ([], "executed") if state == "FOUND" else ([], "data_insufficient")


def _check_currency(dataset, output):
    if output is None or output.summary.get("sample_output_sampling_currency_state") != "FOUND":
        return [], "data_insufficient"
    value = str(output.summary.get("sample_output_sampling_currency") or "").strip()
    normalized = value.replace(" ", "").lower()
    if "本期计提折旧" in normalized or normalized in {"currentdepreciation", "bookdepreciation"}:
        return [], "executed"
    return [_issue(output, "k03_tod_sampling_currency", "sample_output_sampling_currency", Severity.FAIL,
        f"选样输出的抽样货币单元不是本期计提折旧：{value}。", "请使用本期计提折旧作为抽样货币单元。")], "executed"


def _check_te(dataset, output, lead):
    output_te = parse_amount(output.summary.get("sample_output_te")) if output else None
    lead_te = parse_amount(field_values(lead).get("te")) if lead else None
    if output_te is None or lead_te is None:
        return [], "data_insufficient"
    tolerance = max(abs(lead_te), Decimal("1")) * Decimal("0.0001")
    if abs(output_te - lead_te) <= tolerance:
        return [], "executed"
    return [_issue(output, "k03_tod_sampling_te_consistency", "sample_output_te", Severity.FAIL,
        f"选样输出 TE 与 Lead 不一致：选样输出={output_te}，Lead={lead_te}。", "请修正选样参数并与 Lead TE 保持一致。")], "executed"


def _rollforward_depreciation(rollforward):
    amount, row = get_movement_transaction_amount(rollforward, transaction_key="depreciation", measure="accumulated_depreciation")
    if amount is None and rollforward is not None:
        return rollforward.table4_rollforward_depreciation, rollforward.table4_rollforward_depreciation_row
    return amount, row


def _check_population(dataset, lead, rollforward):
    population = parse_amount(dataset.summary.get("tod_population_amount"))
    rf_amount, rf_row = _rollforward_depreciation(rollforward)
    sad = parse_amount(field_values(lead).get("sad")) if lead else None
    if population is None or rf_amount is None or sad is None or sad <= 0:
        return [], "data_insufficient"
    difference = population - rf_amount
    if abs(difference) <= sad:
        return [], "executed"
    explained = _has_project_followup(dataset)
    severity = Severity.NEED_REVIEW if explained else Severity.FAIL
    message = f"TOD 抽样总体与 K.01 折旧金额差异超过 SAD：TOD={population}，K.01={rf_amount}，差异={difference}，SAD={sad}。"
    return [_issue(dataset, "k03_tod_sampling_population_reconciliation", "tod_population_amount", severity,
        message, "请调查差异并记录原因和结论。", source_row=rf_row)], "executed"


def _has_project_followup(dataset: K03SheetDataset) -> bool:
    for row in _main_rows(dataset):
        if str((row.get("values") or {}).get("note") or "").strip():
            return True
    texts = [dataset.summary.get("tod_conclusion_text")]
    area_text = str(dataset.note_area.text if dataset.note_area else "").strip()
    normalized_area = area_text.replace(" ", "").lower()
    if area_text and not (
        "样本类型" in normalized_area
        and "固定资产编号" in normalized_area
        and "notes" in normalized_area
    ):
        texts.append(area_text)
    template_only = {"notes", "note", "说明", "结论", "测试结论"}
    for value in texts:
        text = str(value or "").strip()
        if text and text.lower() not in template_only and len(text) >= 6:
            return True
    return False


def _sampling_rows(dataset, key):
    return list(dataset.summary.get(key) or []) if dataset else []


def _selected_output_rows(output):
    return [row for row in _sampling_rows(output, "sample_output_rows") if row.get("sample_type") in {"key", "representative"}]


def _main_rows(dataset):
    return [row for row in _sampling_rows(dataset, "tod_sampling_rows") if row.get("sample_type") in {"key", "representative", "replacement"}]


def _check_counts(dataset, output):
    if output is None or output.summary.get("sample_output_detail_state") != "FOUND" or dataset.summary.get("tod_sampling_detail_state") != "FOUND":
        return [], "data_insufficient"
    output_rows = _selected_output_rows(output)
    main_rows = _main_rows(dataset)
    expected_key = parse_amount(output.summary.get("sample_output_key_item_count"))
    expected_representative = parse_amount(output.summary.get("sample_output_representative_count"))
    expected_total = parse_amount(output.summary.get("sample_output_selected_count"))
    actual_key = sum(row.get("sample_type") == "key" for row in output_rows)
    actual_representative = sum(row.get("sample_type") == "representative" for row in output_rows)
    mismatch = (
        len(output_rows) != len(main_rows)
        or (expected_key is not None and int(expected_key) != actual_key)
        or (expected_representative is not None and int(expected_representative) != actual_representative)
        or (expected_total is not None and int(expected_total) != len(output_rows))
    )
    if not mismatch:
        return [], "executed"
    return [_issue(dataset, "k03_tod_sampling_count_consistency", "sample_count", Severity.FAIL,
        f"选样输出与主测试样本数量不一致：选定样本={len(output_rows)}，主测试={len(main_rows)}，关键项={actual_key}，代表性样本={actual_representative}。",
        "请核对关键项、代表性样本及实际测试数量。")], "executed"


def _row_ids(rows):
    ids = [str(row.get("asset_id") or "").strip().upper() for row in rows]
    return ids, {value for value in ids if value and ids.count(value) > 1}


def _check_identities(dataset, output):
    if output is None or output.summary.get("sample_output_detail_state") != "FOUND" or dataset.summary.get("tod_sampling_detail_state") != "FOUND":
        return [], "data_insufficient"
    output_rows = _selected_output_rows(output)
    replacement_ids = {row.get("asset_id") for row in _sampling_rows(output, "sample_output_rows") if row.get("sample_type") == "replacement"}
    main_rows = _main_rows(dataset)
    output_ids, output_dupes = _row_ids(output_rows)
    main_ids, main_dupes = _row_ids(main_rows)
    if not all(output_ids) or not all(main_ids):
        return [], "data_insufficient"
    missing = sorted(set(output_ids) - set(main_ids))
    extra = sorted(set(main_ids) - set(output_ids))
    replacement_used = sorted(set(extra) & {str(value or "").upper() for value in replacement_ids})
    issues = []
    unmatched_missing = missing[len(replacement_used):] if replacement_used else missing
    if output_dupes or main_dupes or unmatched_missing or (set(extra) - set(replacement_used)):
        issues.append(_issue(dataset, "k03_tod_sampling_identity_consistency", "asset_id", Severity.FAIL,
            f"选样输出与主测试资产编号不一致：遗漏={unmatched_missing}，额外={sorted(set(extra)-set(replacement_used))}，重复={sorted(output_dupes|main_dupes)}。",
            "请按资产编号核对选样输出与实际测试样本。"))
    if replacement_used:
        issues.append(_issue(dataset, "k03_tod_sampling_identity_consistency", "replacement_sample", Severity.NEED_REVIEW,
            f"主测试使用了替换样本：{replacement_used}。", "请复核替换原因及原样本无法测试的依据。"))
    return issues, "executed"


def _check_attributes(dataset):
    if dataset.summary.get("tod_sampling_detail_state") != "FOUND":
        return [], "data_insufficient"
    issues = []
    for row in _main_rows(dataset):
        values = row.get("values") or {}
        missing = [field for field in ("evidence_description", "test_attribute_1", "test_attribute_2") if not str(values.get(field) or "").strip()]
        if missing:
            issues.append(_issue(dataset, "k03_tod_sampling_attributes", "sample_attributes", Severity.NEED_REVIEW,
                f"样本 {row.get('asset_id') or '未编号'} 缺少测试属性或证据描述：{missing}。", "请补充测试属性结果和支持性证据描述。", source_row=row.get("source_row")))
        abnormal = [field for field in ("test_attribute_1", "test_attribute_2") if str(values.get(field) or "").strip().lower() not in {"", "y", "yes", "是"}]
        if abnormal:
            severity = Severity.NEED_REVIEW if str(values.get("note") or "").strip() else Severity.FAIL
            issues.append(_issue(dataset, "k03_tod_sampling_attributes", "sample_attributes", severity,
                f"样本 {row.get('asset_id')} 存在非满意测试属性：{abnormal}。", "请调查异常属性并在对应样本行记录跟进说明。", source_row=row.get("source_row")))
    return issues, "executed"


def _check_difference_followup(dataset):
    if dataset.summary.get("tod_sampling_detail_state") != "FOUND":
        return [], "data_insufficient"
    issues = []
    if not _main_rows(dataset) or all("depreciation_difference" not in (row.get("values") or {}) for row in _main_rows(dataset)):
        return [], "data_insufficient"
    for row in _main_rows(dataset):
        values = row.get("values") or {}
        raw_difference = values.get("depreciation_difference")
        if raw_difference in (None, ""):
            return [], "data_insufficient"
        difference = parse_amount(raw_difference)
        if difference is None:
            return [], "data_insufficient"
        if difference is not None and abs(difference) > Decimal("0.01"):
            severity = Severity.NEED_REVIEW if str(values.get("note") or "").strip() else Severity.FAIL
            issues.append(_issue(dataset, "k03_tod_sampling_difference_followup", "depreciation_difference", severity,
                f"样本 {row.get('asset_id')} 存在重算差异 {difference}。", "请记录差异调查、处理和结论。", source_row=row.get("source_row")))
    return issues, "executed"


def _check_documentation(dataset):
    issues = []
    if not dataset.summary.get("tod_key_item_reason_text"):
        issues.append(_issue(dataset, "k03_tod_sampling_documentation", "tod_key_item_reason_text", Severity.NEED_REVIEW,
            "未识别到项目化的关键项目选择依据。", "请记录关键项目筛选标准或无关键项目的判断依据。"))
    if not dataset.summary.get("tod_conclusion_text"):
        issues.append(_issue(dataset, "k03_tod_sampling_documentation", "tod_conclusion_text", Severity.NEED_REVIEW,
            "未识别到 TOD 抽样测试结论。", "请记录样本结果和总体结论。"))
    return issues, "executed"


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


def _record_results(
    recorder: RuleExecutionRecorder,
    dataset: K03SheetDataset,
    issues: Iterable[QcIssue],
    statuses: dict[str, str],
    *,
    sample_output: K03SheetDataset | None,
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> None:
    issue_list = list(issues)
    for rule_id in RULE_IDS:
        status = statuses.get(rule_id, "data_insufficient")
        observation = _tod_observation(
            rule_id, dataset, issue_list,
            sample_output=sample_output, lead=lead, rollforward=rollforward,
        )
        if status == "executed":
            recorder.record_executed(
                rule_id,
                sum(1 for issue in issue_list if issue.rule_id == rule_id),
                observation=observation,
            )
        elif status == "not_applicable":
            recorder.record_not_applicable(rule_id, "已由拆分后的 TOD 抽样子规则逐项执行。")
            recorder.record_observation(rule_id, observation)
        else:
            recorder.record_data_insufficient(rule_id, "执行该 TOD 抽样规则所需资料未能可靠识别。")
            recorder.record_observation(rule_id, observation)


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

    observation = _observation(
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
    if sample_output is not None:
        output_rows = sample_output.summary.get("sample_output_rows") or []
        selected_rows = [
            row for row in output_rows
            if row.get("sample_type") in {"key", "representative"}
        ]
        main_rows = _main_rows(dataset)
        output_ids, output_duplicates = _row_ids(selected_rows)
        main_ids, main_duplicates = _row_ids(main_rows)
        replacement_pool = {
            str(row.get("asset_id") or "").strip().upper()
            for row in output_rows
            if row.get("sample_type") == "replacement"
        }
        missing_ids = sorted(set(output_ids) - set(main_ids))
        extra_ids = sorted(set(main_ids) - set(output_ids))
        replacement_used = sorted(set(extra_ids) & replacement_pool)
        observation["checked_data"].append({
            "sheet": sample_output.sheet_name,
            "section": "K.03.2a 折旧选样输出",
            "location": None,
            "identified_by": {
                "sheet_name": sample_output.sheet_name,
                "section": "动态识别的抽样参数区和已选样本表",
                "matched_keywords": ["抽样参数", "样本类型", "固定资产编号"],
                "matched_rows": [row.get("source_row") for row in output_rows[:8]],
                "matched_columns": [],
            },
            "key_columns": ["sample_type", "asset_id", "current_depreciation"],
            "values_read": [
                _value("选定样本数量", sample_output.summary.get("sample_output_selected_rows_count"), None, None, "sample_count"),
                _value("替换样本数量", sample_output.summary.get("sample_output_replacement_rows_count"), None, None, "sample_count"),
                _value("选样输出遗漏编号", missing_ids, None, None, "asset_id_list"),
                _value("主测试额外编号", extra_ids, None, None, "asset_id_list"),
                _value("重复资产编号", sorted(output_duplicates | main_duplicates), None, None, "asset_id_list"),
                _value("实际使用的替换样本", replacement_used, None, None, "asset_id_list"),
            ],
            "missing_data": [] if sample_output.summary.get("sample_output_detail_state") == "FOUND" else ["可可靠识别的已选样本明细表"],
        })
    return observation


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
