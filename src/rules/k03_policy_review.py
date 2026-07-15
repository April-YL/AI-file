from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ingest.k03_sheet import (
    EXECUTION_PATH_POLICY_REVIEW,
    K03PolicyRow,
    K03SheetDataset,
)
from ingest.models import AssetRecord
from ingest.records import FaListDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.k03_observations import (
    K03_LOW_RISK_HOW_RULE_IDS,
    build_k03_not_applicable_observation,
    build_k03_policy_low_risk_observation,
)
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_IDS: tuple[str, ...] = (
    "k03_policy_three_elements_complete",
    "k03_policy_method_change_consistency",
    "k03_policy_annual_rate_recalculation",
    "k03_policy_period_consistency",
    "k03_policy_change_field_explanation",
    "k03_policy_fa_category_coverage",
    "k03_policy_fa_life_exception_followup",
    "k03_policy_fa_salvage_exception_followup",
    "k03_policy_conclusion_consistency",
)

_MAX_DETAIL_FINDINGS = 5
_RATE_TOL = Decimal("0.0001")
_LIFE_UNIT_RATE_TOL = Decimal("0.005")
_EXTREME_LIFE_MONTHS = Decimal("1200")
_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "tbd",
    "todo",
    "na",
    "n/a",
    "none",
    "待补",
    "待定",
    "未完成",
    "待说明",
    "待解释",
    "不适用",
}


@dataclass(frozen=True)
class LifeRange:
    min_months: Decimal
    max_months: Decimal
    unit_known: bool = True


@dataclass(frozen=True)
class RateRange:
    min_rate: Decimal
    max_rate: Decimal


def run_k03_policy_review_rules(
    dataset: K03SheetDataset | None,
    *,
    fa_list: FaListDataset | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    return _run_k03_policy_p1(dataset, fa_list=fa_list, recorder=recorder)


def _run_k03_policy_p1(
    dataset: K03SheetDataset | None,
    *,
    fa_list: FaListDataset | None,
    recorder: RuleExecutionRecorder,
) -> list[QcIssue]:
    if dataset is None:
        _record_k03_policy_execution(recorder, [], RULE_IDS, dataset=None, fa_list=fa_list)
        return []
    if dataset.execution_path != EXECUTION_PATH_POLICY_REVIEW:
        note = "The current K.03 sheet is not the depreciation-policy review path."
        for rule_id in RULE_IDS:
            recorder.record_not_applicable(rule_id, note)
        return []
    if dataset.policy_table is None or not dataset.policy_table.rows:
        _record_k03_policy_execution(recorder, [], RULE_IDS, dataset=dataset, fa_list=fa_list)
        return []

    issues: list[QcIssue] = []
    issues.extend(_check_structure(dataset))
    issues.extend(_check_method_change_consistency(dataset))
    issues.extend(_check_annual_rate_recalculation(dataset))
    issues.extend(_check_policy_period_dates(dataset))
    issues.extend(_check_policy_rows(dataset))
    issues.extend(_check_fa_list_consistency(dataset, fa_list))
    issues.extend(_check_conclusion_consistency(dataset))
    _record_k03_policy_execution(recorder, issues, RULE_IDS, dataset=dataset, fa_list=fa_list)
    return issues

    # Legacy implementation below is intentionally unreachable while the P1
    # rule set is migrated in-place; retained helpers are reused by P1.
    if dataset is None:
        issues = [
            QcIssue(
                asset_id=None,
                rule_id="k03_policy_sheet_missing",
                field="sheet",
                severity=Severity.NEED_REVIEW,
                message="K.03.3折旧政策复核页未识别。",
                suggestion="请人工确认底稿是否包含 K.03.3 折旧政策复核页。",
                procedure_code="K.03.3",
                source_sheet="K.03.3 折旧政策复核",
            )
        ]
        _record_k03_policy_execution(
            recorder,
            issues,
            RULE_IDS,
            dataset=None,
            fa_list=fa_list,
        )
        return issues
    if dataset.execution_path != EXECUTION_PATH_POLICY_REVIEW:
        note = "当前 K.03 工作表不是折旧政策复核执行路径"
        for rule_id in RULE_IDS:
            recorder.record_not_applicable(rule_id, note)
            if rule_id in K03_LOW_RISK_HOW_RULE_IDS:
                recorder.record_observation(
                    rule_id,
                    build_k03_not_applicable_observation(rule_id, dataset, reason=note),
                )
        return []

    issues: list[QcIssue] = []
    table = dataset.policy_table
    if table is None or not table.rows:
        issues = [
            _issue(
                dataset,
                "k03_policy_table_unreadable",
                "policy_table",
                Severity.NEED_REVIEW,
                "K.03.3 折旧政策表 1 未能识别或解析。",
                "请复核该页是否包含资产类别、本期/上期政策、差异判断和 Notes/说明等栏目。",
                source_row=table.header_row if table else None,
            )
        ]
        _record_k03_policy_execution(
            recorder,
            issues,
            RULE_IDS,
            dataset=dataset,
            fa_list=fa_list,
        )
        return issues

    issues.extend(_check_structure(dataset))
    issues.extend(_check_policy_rows(dataset))
    issues.extend(_check_fa_list_consistency(dataset, fa_list))
    _record_k03_policy_execution(recorder, issues, RULE_IDS, dataset=dataset, fa_list=fa_list)
    return issues


def _record_k03_policy_execution(
    recorder: RuleExecutionRecorder,
    issues: list[QcIssue],
    rule_ids: tuple[str, ...],
    *,
    dataset: K03SheetDataset | None,
    fa_list: FaListDataset | None,
) -> None:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.rule_id] = counts.get(issue.rule_id, 0) + 1
    for rule_id in rule_ids:
        missing_data = _policy_rule_missing_data(rule_id, dataset, fa_list)
        observation = None
        if rule_id in K03_LOW_RISK_HOW_RULE_IDS:
            observation = build_k03_policy_low_risk_observation(
                rule_id,
                dataset,
                issues,
                fa_list=fa_list,
                additional_missing_data=missing_data,
            )
        if missing_data and not counts.get(rule_id, 0):
            recorder.record_data_insufficient(rule_id, "; ".join(missing_data))
            if observation is not None:
                recorder.record_observation(rule_id, observation)
        else:
            recorder.record_executed(rule_id, counts.get(rule_id, 0), observation=observation)


def _policy_rule_missing_data(
    rule_id: str,
    dataset: K03SheetDataset | None,
    fa_list: FaListDataset | None,
) -> list[str]:
    return _p1_policy_rule_missing_data(rule_id, dataset, fa_list)


def _p1_policy_rule_missing_data(
    rule_id: str,
    dataset: K03SheetDataset | None,
    fa_list: FaListDataset | None,
) -> list[str]:
    if dataset is None:
        return ["K.03.3 policy-review sheet was not identified."]
    table = dataset.policy_table
    if table is None or not table.rows:
        return ["K.03.3 policy table could not be read."]

    fields = set(table.column_map)
    unit = _infer_policy_life_unit(table)
    if rule_id == "k03_policy_three_elements_complete":
        required = {"asset_category", "current_useful_life", "current_salvage_rate"}
        missing = required - fields
        if is_blank(_policy_method(table, "current")):
            missing.add("current_method")
        return ["Missing policy elements: " + ", ".join(sorted(missing))] if missing else []
    if rule_id == "k03_policy_method_change_consistency":
        if any(is_blank(value) for value in (table.current_method, table.prior_method, table.method_same_marker)):
            return ["Current/prior method or method comparison marker is unavailable."]
        return []
    if rule_id == "k03_policy_annual_rate_recalculation":
        if not any(_row_has_annual_rate_inputs(row, unit) for row in table.rows):
            return ["No row has comparable life, salvage rate and annual depreciation rate."]
        return []
    if rule_id == "k03_policy_period_consistency":
        if is_blank(table.current_policy_date) or is_blank(table.prior_policy_date):
            return ["Current or prior policy date is unavailable."]
        if not any(_row_has_period_inputs(row, unit) for row in table.rows):
            return ["Current/prior policy values or comparison markers are unavailable."]
        return []
    if rule_id == "k03_policy_change_field_explanation":
        if not any(_row_has_comparable_policy_values(row, unit, fields) for row in table.rows):
            return ["No comparable current/prior policy fields were identified."]
        return []
    if rule_id == "k03_policy_conclusion_consistency":
        if dataset.note_area is None or not _norm_text(dataset.note_area.text):
            return ["Policy-review conclusion or Notes body was not identified."]
        return []
    if rule_id in {
        "k03_policy_fa_category_coverage",
        "k03_policy_fa_life_exception_followup",
        "k03_policy_fa_salvage_exception_followup",
    }:
        if fa_list is None or not fa_list.records:
            return ["FA list is unavailable."]
        if rule_id == "k03_policy_fa_category_coverage":
            if "asset_category" not in fields:
                return ["Policy asset-category field is unavailable."]
            return []
        if rule_id == "k03_policy_fa_life_exception_followup":
            return [] if _has_comparable_fa_life(table, fa_list) else ["No comparable policy/FA useful-life inputs."]
        return [] if _has_comparable_fa_salvage(table, fa_list) else ["No comparable policy/FA salvage-rate inputs."]
    return []


def _row_has_annual_rate_inputs(row: K03PolicyRow, unit: str | None) -> bool:
    return (
        parse_life_range(row.current_useful_life, assume_number_unit=unit) is not None
        and parse_rate_range(row.current_salvage_rate) is not None
        and parse_rate_range(row.current_annual_rate) is not None
    )


def _policy_method(table: object, period: str) -> object:
    field = f"{period}_method"
    value = getattr(table, field, None)
    if not is_blank(value):
        return value
    for row in getattr(table, "rows", []):
        value = getattr(row, field, None)
        if not is_blank(value):
            return value
    return None


def _row_has_period_inputs(row: K03PolicyRow, unit: str | None) -> bool:
    life_pair = (
        parse_life_range(row.current_useful_life, assume_number_unit=unit),
        parse_life_range(row.prior_useful_life, assume_number_unit=unit),
    )
    salvage_pair = (
        parse_rate_range(row.current_salvage_rate),
        parse_rate_range(row.prior_salvage_rate),
    )
    return bool(
        (all(life_pair) and not is_blank(row.useful_life_same_marker))
        or (all(salvage_pair) and not is_blank(row.salvage_rate_same_marker))
    )

    # Legacy P0 missing-data routing below is unreachable.
    if dataset is None:
        return [] if rule_id == "k03_policy_sheet_missing" else ["未识别 K.03.3 折旧政策复核工作表"]
    if rule_id == "k03_policy_sheet_missing":
        return []
    table = dataset.policy_table
    if table is None or not table.rows:
        return [] if rule_id == "k03_policy_table_unreadable" else ["未能读取 K.03.3 折旧政策表"]
    if rule_id in {"k03_policy_table_unreadable", "k03_policy_sections_incomplete"}:
        return []

    fields = set(table.column_map)
    if rule_id == "k03_policy_difference_marker":
        evaluable = False
        missing_marker = False
        for row in table.rows:
            for current, prior, marker, required in (
                (
                    row.current_useful_life,
                    row.prior_useful_life,
                    row.useful_life_same_marker,
                    {"current_useful_life", "prior_useful_life", "useful_life_same_marker"},
                ),
                (
                    row.current_salvage_rate,
                    row.prior_salvage_rate,
                    row.salvage_rate_same_marker,
                    {"current_salvage_rate", "prior_salvage_rate", "salvage_rate_same_marker"},
                ),
            ):
                if not required <= fields or is_blank(current) or is_blank(prior):
                    continue
                evaluable = True
                if is_blank(marker):
                    missing_marker = True
        if not evaluable:
            return ["缺少本期、上期及差异标记的可比政策字段"]
        if missing_marker:
            return ["差异标记为空或公式没有缓存值"]
        return []
    if rule_id == "k03_policy_change_without_explanation":
        unit = _infer_policy_life_unit(table)
        if not any(_row_has_comparable_policy_values(row, unit, fields) for row in table.rows):
            return ["缺少可比较的本期和上期政策字段"]
        return []
    if rule_id == "k03_policy_obvious_anomaly":
        if not fields & {"current_useful_life", "current_salvage_rate"}:
            return ["缺少本期使用寿命和残值率字段"]
        return []
    if rule_id in {
        "k03_policy_fa_life_out_of_range",
        "k03_policy_fa_salvage_mismatch",
        "k03_policy_fa_unit_or_category_review",
    }:
        if fa_list is None or not fa_list.records:
            return ["缺少可用 FA list"]
        if rule_id == "k03_policy_fa_unit_or_category_review":
            if "asset_category" not in fields:
                return ["政策表缺少资产类别字段"]
            return []
        if rule_id == "k03_policy_fa_life_out_of_range":
            if not _has_comparable_fa_life(table, fa_list):
                return ["政策或 FA list 使用寿命无法按唯一单位完成比较"]
            return []
        if not _has_comparable_fa_salvage(table, fa_list):
            return ["政策或 FA list 残值率无法完成比较"]
    return []


def _row_has_comparable_policy_values(
    row: K03PolicyRow,
    unit: str | None,
    fields: set[str],
) -> bool:
    life_pair = (
        parse_life_range(row.current_useful_life, assume_number_unit=unit),
        parse_life_range(row.prior_useful_life, assume_number_unit=unit),
    )
    rate_pair = (parse_rate_range(row.current_salvage_rate), parse_rate_range(row.prior_salvage_rate))
    return bool(
        ({"current_useful_life", "prior_useful_life"} <= fields and all(life_pair))
        or ({"current_salvage_rate", "prior_salvage_rate"} <= fields and all(rate_pair))
        or (
            {"current_method", "prior_method"} <= fields
            and _norm_text(row.current_method)
            and _norm_text(row.prior_method)
        )
        or (
            {"current_annual_rate", "prior_annual_rate"} <= fields
            and _norm_text(row.current_annual_rate)
            and _norm_text(row.prior_annual_rate)
        )
    )


def _check_structure(dataset: K03SheetDataset) -> list[QcIssue]:
    table = dataset.policy_table
    if table is None:
        return []
    fields = set(table.column_map)
    issues: list[QcIssue] = []
    required_groups = {
        "asset_category": {"asset_category"},
        "useful_life": {"current_useful_life"},
        "salvage_rate": {"current_salvage_rate"},
    }
    for group, candidates in required_groups.items():
        if not (fields & candidates):
            issues.append(
                _issue(
                    dataset,
                    "k03_policy_three_elements_complete",
                    group,
                    Severity.NEED_REVIEW,
                    f"K.03.3 折旧政策表缺少或无法映射 {group} 相关栏目。",
                    "请确认表 1 是否完整列示本期政策、上期政策和差异判断/说明区。",
                    source_row=table.header_row,
                )
            )
    if is_blank(_policy_method(table, "current")):
        issues.append(
            _issue(
                dataset,
                "k03_policy_three_elements_complete",
                "current_method",
                Severity.WARN,
                "The current-period depreciation method is missing.",
                "Complete the depreciation method before concluding on the policy review.",
                source_row=_cell_row(table.context_cell_refs.get("current_method")) or table.header_row,
                source_col=_cell_col(table.context_cell_refs.get("current_method")),
            )
        )
    return issues
    if dataset.note_area is None:
        issues.append(
            _issue(
                dataset,
                "k03_policy_three_elements_complete",
                "note_area",
                Severity.WARN,
                "未识别到 K.03.3 Notes/说明区。",
                "如折旧政策存在变化，请在差异说明列或 Notes 区补充原因和结论。",
                source_row=table.range.end_row if table.range else table.header_row,
            )
        )
    return issues


def _check_policy_rows(dataset: K03SheetDataset) -> list[QcIssue]:
    assert dataset.policy_table is not None
    sheet_explained = _has_valid_note(dataset)
    life_unit = _infer_policy_life_unit(dataset.policy_table)
    issues: list[QcIssue] = []
    for row in dataset.policy_table.rows:
        changed_fields = _changed_policy_fields(row, life_unit)
        same_fields = _same_policy_fields(row, life_unit)
        issues.extend(_check_policy_anomalies(dataset, row, life_unit))

        if (
            "useful_life" in same_fields
            and not is_blank(row.useful_life_same_marker)
            and not _marker_is_true(row.useful_life_same_marker)
        ):
            issues.append(
                _policy_row_issue(
                    dataset,
                    row,
                    "k03_policy_period_consistency",
                    "useful_life_same_marker",
                    Severity.WARN,
                    "本期与上期使用寿命看起来一致，但差异标记未显示为 TRUE 或等同含义。",
                    "请检查使用寿命差异公式或标记是否正确。",
                )
            )
        if (
            "salvage_rate" in same_fields
            and not is_blank(row.salvage_rate_same_marker)
            and not _marker_is_true(row.salvage_rate_same_marker)
        ):
            issues.append(
                _policy_row_issue(
                    dataset,
                    row,
                    "k03_policy_period_consistency",
                    "salvage_rate_same_marker",
                    Severity.WARN,
                    "本期与上期残值率看起来一致，但差异标记未显示为 TRUE 或等同含义。",
                    "请检查残值率差异公式或标记是否正确。",
                )
            )

        if "useful_life" in changed_fields and _marker_is_true(row.useful_life_same_marker):
            issues.append(
                _policy_row_issue(
                    dataset,
                    row,
                    "k03_policy_period_consistency",
                    "useful_life_same_marker",
                    Severity.WARN,
                    "使用寿命较上期发生变化，但差异标记仍显示为 TRUE。",
                    "请确认该折旧政策变化是否已被正确识别并说明。",
                )
            )
        if "salvage_rate" in changed_fields and _marker_is_true(row.salvage_rate_same_marker):
            issues.append(
                _policy_row_issue(
                    dataset,
                    row,
                    "k03_policy_period_consistency",
                    "salvage_rate_same_marker",
                    Severity.WARN,
                    "残值率较上期发生变化，但差异标记仍显示为 TRUE。",
                    "请确认该折旧政策变化是否已被正确识别并说明。",
                )
            )
        if changed_fields and not (sheet_explained or _has_valid_explanation(row.difference_explanation)):
            issues.append(
                _policy_row_issue(
                    dataset,
                    row,
                    "k03_policy_change_field_explanation",
                    "difference_explanation",
                    Severity.FAIL,
                    "本期与上期折旧政策存在差异，但未识别到有效差异说明或 Notes。",
                    "请针对折旧政策变化补充差异说明或 Notes，说明原因和处理结论。",
                )
            )
    return issues


def _check_method_change_consistency(dataset: K03SheetDataset) -> list[QcIssue]:
    table = dataset.policy_table
    if table is None:
        return []
    current = _norm_text(_policy_method(table, "current"))
    prior = _norm_text(_policy_method(table, "prior"))
    marker = table.method_same_marker
    if not current or not prior or is_blank(marker):
        return []
    same = current == prior
    marker_same = _marker_is_true(marker)
    if same == marker_same:
        return []
    return [
        _issue(
            dataset,
            "k03_policy_method_change_consistency",
            "method_same_marker",
            Severity.WARN,
            "The current/prior depreciation methods do not agree with the method comparison marker.",
            "Recheck the method comparison formula and explain any method change.",
            source_row=_cell_row(table.context_cell_refs.get("method_same_marker")),
            source_col=_cell_col(table.context_cell_refs.get("method_same_marker")),
        )
    ]


def _check_annual_rate_recalculation(dataset: K03SheetDataset) -> list[QcIssue]:
    table = dataset.policy_table
    if table is None:
        return []
    unit = _infer_policy_life_unit(table)
    issues: list[QcIssue] = []
    for row in table.rows:
        for period, life_value, salvage_value, annual_value in (
            ("current", row.current_useful_life, row.current_salvage_rate, row.current_annual_rate),
            ("prior", row.prior_useful_life, row.prior_salvage_rate, row.prior_annual_rate),
        ):
            life = parse_life_range(life_value, assume_number_unit=unit)
            salvage = parse_rate_range(salvage_value)
            annual = parse_rate_range(annual_value)
            if life is None or salvage is None or annual is None or life.min_months <= 0:
                continue
            min_years = life.min_months / Decimal("12")
            max_years = life.max_months / Decimal("12")
            expected_min = (Decimal("1") - salvage.max_rate) / max_years
            expected_max = (Decimal("1") - salvage.min_rate) / min_years
            if (
                annual.min_rate < expected_min - _LIFE_UNIT_RATE_TOL
                or annual.max_rate > expected_max + _LIFE_UNIT_RATE_TOL
            ):
                issues.append(
                    _policy_row_issue(
                        dataset,
                        row,
                        "k03_policy_annual_rate_recalculation",
                        f"{period}_annual_rate",
                        Severity.WARN,
                        "The stated annual depreciation rate does not recalculate from useful life and salvage rate.",
                        "Recalculate the annual rate and document any approved exception.",
                    )
                )
    return issues


def _check_policy_period_dates(dataset: K03SheetDataset) -> list[QcIssue]:
    table = dataset.policy_table
    if table is None:
        return []
    current = _as_date(table.current_policy_date)
    prior = _as_date(table.prior_policy_date)
    if current is None or prior is None or current > prior:
        return []
    return [
        _issue(
            dataset,
            "k03_policy_period_consistency",
            "policy_date",
            Severity.FAIL,
            "The current policy date is not later than the prior policy date.",
            "Correct the current/prior period headings before concluding on policy consistency.",
            source_row=_cell_row(table.context_cell_refs.get("current_policy_date")),
            source_col=_cell_col(table.context_cell_refs.get("current_policy_date")),
        )
    ]


def _check_conclusion_consistency(dataset: K03SheetDataset) -> list[QcIssue]:
    table = dataset.policy_table
    if table is None or dataset.note_area is None:
        return []
    note = _norm_text(dataset.note_area.text)
    if not note:
        return []
    unit = _infer_policy_life_unit(table)
    changed = set().union(*(_changed_policy_fields(row, unit) for row in table.rows)) if table.rows else set()
    no_change = any(token in note for token in ("无变化", "未发生变化", "未改变", "一致"))
    change_explained = any(token in note for token in ("差异", "调整", "变更", "改变"))
    if changed and no_change and not change_explained:
        return [
            _issue(
                dataset,
                "k03_policy_conclusion_consistency",
                "note_area",
                Severity.WARN,
                "The conclusion states that policy did not change, but comparable policy fields changed.",
                "Revise the conclusion or explain the identified policy changes.",
                source_row=dataset.note_area.start_row,
                source_col=dataset.note_area.start_col,
            )
        ]
    if not changed and change_explained and not no_change:
        return [
            _issue(
                dataset,
                "k03_policy_conclusion_consistency",
                "note_area",
                Severity.NEED_REVIEW,
                "The conclusion describes a policy change that is not reflected in the comparison table.",
                "Reconcile the conclusion to the current/prior policy fields.",
                source_row=dataset.note_area.start_row,
                source_col=dataset.note_area.start_col,
            )
        ]
    return []


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10] if not is_blank(value) else ""
    try:
        return datetime.fromisoformat(text).date() if text else None
    except ValueError:
        return None


def _cell_row(ref: str | None) -> int | None:
    match = re.search(r"(\d+)$", ref or "")
    return int(match.group(1)) if match else None


def _cell_col(ref: str | None) -> int | None:
    match = re.match(r"([A-Z]+)", ref or "")
    if not match:
        return None
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - 64
    return result


def _check_fa_list_consistency(
    dataset: K03SheetDataset,
    fa_list: FaListDataset | None,
) -> list[QcIssue]:
    if fa_list is None or not fa_list.records:
        return []
    if dataset.policy_table is None:
        return []

    life_unit = _infer_policy_life_unit(dataset.policy_table)

    policy_by_category = {
        _category_key(row.asset_category): row
        for row in dataset.policy_table.rows
        if _category_key(row.asset_category)
    }
    issues: list[QcIssue] = []
    category_review_count = 0
    life_findings = 0
    salvage_findings = 0
    anomaly_findings = 0
    for rec in fa_list.records:
        category_key = _category_key(rec.asset_category)
        if not category_key:
            if _has_policy_comparison_value(rec):
                category_review_count += 1
            continue
        policy = policy_by_category.get(category_key)
        if policy is None:
            if _has_policy_comparison_value(rec):
                category_review_count += 1
            continue

        life_issue = _fa_life_issue(dataset, fa_list, rec, policy, life_unit)
        if life_issue and life_findings < _MAX_DETAIL_FINDINGS:
            issues.append(life_issue)
            life_findings += 1
        elif life_issue:
            life_findings += 1

        salvage_issue = _fa_salvage_issue(dataset, fa_list, rec, policy)
        if salvage_issue and salvage_findings < _MAX_DETAIL_FINDINGS:
            issues.append(salvage_issue)
            salvage_findings += 1
        elif salvage_issue:
            salvage_findings += 1

        for anomaly in ():
            if anomaly_findings < _MAX_DETAIL_FINDINGS:
                issues.append(anomaly)
            anomaly_findings += 1

    if category_review_count:
        issues.append(
            _issue(
                dataset,
                "k03_policy_fa_category_coverage",
                "asset_category",
                Severity.NEED_REVIEW,
                f"有 {category_review_count} 行 FA list 资产类别无法匹配到 K.03.3 折旧政策类别。",
                "请复核资产类别命名是否一致；如属于模板差异，后续可补充类别映射表。",
                source_sheet=fa_list.source_sheet,
            )
        )
    for count, rule_id, field in (
        (life_findings, "k03_policy_fa_life_exception_followup", "useful_life_months"),
        (salvage_findings, "k03_policy_fa_salvage_exception_followup", "salvage_rate"),
    ):
        if count > _MAX_DETAIL_FINDINGS:
            issues.append(
                _issue(
                    dataset,
                    rule_id,
                    field,
                    Severity.WARN,
                    f"有 {count} 行 FA list 触发 {field} 相关提示，当前仅展示前 {_MAX_DETAIL_FINDINGS} 条明细。",
                    "请复核所有受影响的 FA list 行，确认折旧政策是否一致或是否已有合理说明。",
                    source_sheet=fa_list.source_sheet,
                )
            )
    return issues


def _has_policy_comparison_value(record: AssetRecord) -> bool:
    return (
        parse_life_range(record.useful_life_months, assume_number_unit="month") is not None
        or parse_rate(record.salvage_rate) is not None
    )


def _fa_list_field_col(fa_list: FaListDataset, field: str) -> int | None:
    for mapping in fa_list.mapped_fields:
        if getattr(mapping, "standard_field", None) == field:
            return getattr(mapping, "column_index", None)
    return None


def _fa_life_issue(
    dataset: K03SheetDataset,
    fa_list: FaListDataset,
    rec: AssetRecord,
    policy: K03PolicyRow,
    policy_unit: str | None,
) -> QcIssue | None:
    policy_range = parse_life_range(policy.current_useful_life, assume_number_unit=policy_unit)
    asset_life = parse_life_range(rec.useful_life_months, assume_number_unit="month")
    if policy_range is None:
        return None
    if asset_life is None:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_life_exception_followup",
            field="useful_life_months",
            severity=Severity.NEED_REVIEW,
            message="无法解析使用寿命，不能完成 K.03.3 折旧政策与 FA list 的使用寿命比对。",
            suggestion="请确认使用寿命是按年还是按月列示，并检查该字段是否存在非标准格式。",
            procedure_code="K.03.3",
            source_sheet=fa_list.source_sheet,
            source_row=rec.source_row,
            source_col=_fa_list_field_col(fa_list, "useful_life_months"),
        )
    months = asset_life.min_months
    if months < policy_range.min_months or months > policy_range.max_months:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_life_exception_followup",
            field="useful_life_months",
            severity=Severity.WARN,
            message=(
                f"FA list 使用寿命超出 K.03.3 折旧政策范围：资产类别={rec.asset_category}，"
                f"资产使用寿命={rec.useful_life_months}，政策范围={policy.current_useful_life}。"
            ),
            suggestion="请检查 FA list 使用寿命是否正确；如该差异合理，请在折旧政策表中补充说明。",
            procedure_code="K.03.3",
            source_sheet=fa_list.source_sheet,
            source_row=rec.source_row,
            source_col=_fa_list_field_col(fa_list, "useful_life_months"),
        )
    return None


def _fa_salvage_issue(
    dataset: K03SheetDataset,
    fa_list: FaListDataset,
    rec: AssetRecord,
    policy: K03PolicyRow,
) -> QcIssue | None:
    policy_range = parse_rate_range(policy.current_salvage_rate)
    asset_rate = parse_rate(rec.salvage_rate)
    if policy_range is None:
        return None
    if asset_rate is None:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_salvage_exception_followup",
            field="salvage_rate",
            severity=Severity.NEED_REVIEW,
            message="无法解析残值率，不能完成 K.03.3 折旧政策与 FA list 的残值率比对。",
            suggestion="请确认残值率是按百分比还是小数列示，并检查该字段是否存在非标准格式。",
            procedure_code="K.03.3",
            source_sheet=fa_list.source_sheet,
            source_row=rec.source_row,
            source_col=_fa_list_field_col(fa_list, "salvage_rate"),
        )
    if asset_rate < policy_range.min_rate or asset_rate > policy_range.max_rate:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_salvage_exception_followup",
            field="salvage_rate",
            severity=Severity.WARN,
            message=(
                f"FA list 残值率与 K.03.3 折旧政策不一致：资产类别={rec.asset_category}，"
                f"资产残值率={rec.salvage_rate}，政策残值率={policy.current_salvage_rate}。"
            ),
            suggestion="请检查 FA list 残值率是否正确；如该资产采用不同残值率，请补充原因说明。",
            procedure_code="K.03.3",
            source_sheet=fa_list.source_sheet,
            source_row=rec.source_row,
            source_col=_fa_list_field_col(fa_list, "salvage_rate"),
        )
    return None


def _fa_anomaly_issues(
    dataset: K03SheetDataset,
    fa_list: FaListDataset,
    rec: AssetRecord,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    life = parse_life_range(rec.useful_life_months, assume_number_unit="month")
    if is_blank(rec.useful_life_months):
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list 使用寿命为空。"))
    elif life is None:
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list 使用寿命单位或格式无法解析。"))
    elif life.min_months <= 0:
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list 使用寿命为 0 或负数。"))
    elif life.max_months > _EXTREME_LIFE_MONTHS:
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list 使用寿命异常偏高，需要复核。"))

    rate = parse_rate(rec.salvage_rate)
    if is_blank(rec.salvage_rate):
        issues.append(_fa_anomaly(fa_list, rec, "salvage_rate", "FA list 残值率为空。"))
    elif rate is None:
        issues.append(_fa_anomaly(fa_list, rec, "salvage_rate", "FA list 残值率无法解析或不在 0-100% 范围内。"))
    elif rate < 0 or rate > 1:
        issues.append(_fa_anomaly(fa_list, rec, "salvage_rate", "FA list 残值率不在 0-100% 范围内。"))
    return issues


def _fa_anomaly(
    fa_list: FaListDataset,
    rec: AssetRecord,
    field: str,
    message: str,
) -> QcIssue:
    return QcIssue(
        asset_id=rec.asset_id or rec.identity(),
        rule_id="k03_policy_obvious_anomaly",
        field=field,
        severity=Severity.WARN,
        message=message,
        suggestion="请先复核 FA list 中该字段取值，再判断是否适用详细折旧政策比对。",
        procedure_code="K.03.3",
        source_sheet=fa_list.source_sheet,
        source_row=rec.source_row,
    )


def _changed_policy_fields(row: K03PolicyRow, life_unit: str | None = None) -> set[str]:
    changed: set[str] = set()
    current_life = parse_life_range(row.current_useful_life, assume_number_unit=life_unit)
    prior_life = parse_life_range(row.prior_useful_life, assume_number_unit=life_unit)
    if current_life and prior_life and current_life != prior_life:
        changed.add("useful_life")
    current_rate = parse_rate_range(row.current_salvage_rate)
    prior_rate = parse_rate_range(row.prior_salvage_rate)
    if current_rate is not None and prior_rate is not None and not _rate_ranges_equal(current_rate, prior_rate):
        changed.add("salvage_rate")
    if _norm_text(row.current_method) and _norm_text(row.prior_method) and _norm_text(row.current_method) != _norm_text(row.prior_method):
        changed.add("method")
    if _norm_text(row.current_annual_rate) and _norm_text(row.prior_annual_rate) and _norm_text(row.current_annual_rate) != _norm_text(row.prior_annual_rate):
        changed.add("annual_rate")
    return changed


def _same_policy_fields(row: K03PolicyRow, life_unit: str | None = None) -> set[str]:
    same: set[str] = set()
    current_life = parse_life_range(row.current_useful_life, assume_number_unit=life_unit)
    prior_life = parse_life_range(row.prior_useful_life, assume_number_unit=life_unit)
    if current_life and prior_life and current_life == prior_life:
        same.add("useful_life")
    current_rate = parse_rate_range(row.current_salvage_rate)
    prior_rate = parse_rate_range(row.prior_salvage_rate)
    if current_rate is not None and prior_rate is not None and _rate_ranges_equal(current_rate, prior_rate):
        same.add("salvage_rate")
    return same


def _check_policy_anomalies(
    dataset: K03SheetDataset,
    row: K03PolicyRow,
    life_unit: str | None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    life = parse_life_range(row.current_useful_life, assume_number_unit=life_unit)
    if is_blank(row.current_useful_life):
        issues.append(_policy_row_issue(dataset, row, "k03_policy_three_elements_complete", "current_useful_life", Severity.WARN, "折旧政策中的本期使用寿命为空。", "请补充本期使用寿命范围。"))
    elif life is None:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_three_elements_complete", "current_useful_life", Severity.NEED_REVIEW, "折旧政策中的本期使用寿命无法解析。", "请确认政策使用寿命是按年还是按月列示，并检查格式是否标准。"))
    elif life.min_months <= 0:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_three_elements_complete", "current_useful_life", Severity.FAIL, "折旧政策中的本期使用寿命为 0 或负数。", "请更正本期使用寿命。"))
    elif life.max_months > _EXTREME_LIFE_MONTHS:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_three_elements_complete", "current_useful_life", Severity.NEED_REVIEW, "折旧政策中的本期使用寿命异常偏高。", "请复核该政策寿命是否合理。"))

    rate = parse_rate_range(row.current_salvage_rate)
    if is_blank(row.current_salvage_rate):
        issues.append(_policy_row_issue(dataset, row, "k03_policy_three_elements_complete", "current_salvage_rate", Severity.WARN, "折旧政策中的本期残值率为空。", "请补充本期残值率。"))
    elif rate is None or rate.min_rate < 0 or rate.max_rate > 1:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_three_elements_complete", "current_salvage_rate", Severity.WARN, "折旧政策中的本期残值率无法解析或不在 0-100% 范围内。", "请更正本期残值率。"))
    return issues


def parse_life_range(value: object, *, assume_number_unit: str | None) -> LifeRange | None:
    if is_blank(value):
        return None
    text = str(value).strip().lower()
    normalized = text.replace("－", "-").replace("—", "-").replace("至", "-").replace("到", "-")
    nums = [Decimal(x) for x in re.findall(r"\d+(?:\.\d+)?", normalized)]
    if not nums:
        return None
    has_month = "月" in normalized or "month" in normalized
    has_year = "年" in normalized or "year" in normalized
    if not has_month and not has_year:
        if assume_number_unit == "month":
            has_month = True
        elif assume_number_unit == "year":
            has_year = True
        else:
            return None
    factor = Decimal("1") if has_month else Decimal("12")
    values = [n * factor for n in nums[:2]]
    if len(values) == 1:
        values.append(values[0])
    lo, hi = min(values), max(values)
    return LifeRange(lo, hi)


def parse_rate(value: object) -> Decimal | None:
    parsed = parse_rate_range(value)
    if parsed is None or parsed.min_rate != parsed.max_rate:
        return None
    amount = parsed.min_rate
    if amount < 0 or amount > 1:
        return None
    return amount


def parse_rate_range(value: object) -> RateRange | None:
    if is_blank(value):
        return None
    text = (
        str(value)
        .strip()
        .replace(",", "")
        .replace("％", "%")
        .replace("－", "-")
        .replace("—", "-")
        .replace("至", "-")
        .replace("到", "-")
    )
    has_percent = "%" in text or "％" in text
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return None
    try:
        amounts = [Decimal(number) for number in numbers[:2]]
    except (InvalidOperation, ValueError):
        return None
    if len(amounts) == 1 and text.lstrip().startswith("-"):
        amounts[0] = -amounts[0]
    normalized: list[Decimal] = []
    for amount in amounts:
        normalized.append(amount / Decimal("100") if has_percent or abs(amount) > 1 else amount)
    if len(normalized) == 1:
        normalized.append(normalized[0])
    return RateRange(min(normalized), max(normalized))


def _rate_ranges_equal(left: RateRange, right: RateRange) -> bool:
    return (
        abs(left.min_rate - right.min_rate) <= _RATE_TOL
        and abs(left.max_rate - right.max_rate) <= _RATE_TOL
    )


def _infer_policy_life_unit(table: object) -> str | None:
    if not hasattr(table, "rows") or not hasattr(table, "column_map"):
        return None
    units: set[str] = set()
    for field in ("current_useful_life", "prior_useful_life"):
        column = table.column_map.get(field)
        header = column.source_header if column else ""
        normalized_header = str(header).lower()
        if re.search(r"单位\s*[:：]?\s*年|[（(]\s*年\s*[）)]|\byears?\b", normalized_header):
            units.add("year")
        if re.search(r"单位\s*[:：]?\s*月|[（(]\s*月\s*[）)]|\bmonths?\b", normalized_header):
            units.add("month")
    for row in table.rows:
        for value in (row.current_useful_life, row.prior_useful_life):
            text = str(value).lower() if not is_blank(value) else ""
            if "月" in text or "month" in text:
                units.add("month")
            if "年" in text or "year" in text:
                units.add("year")
    if len(units) == 1:
        return next(iter(units))
    if len(units) > 1:
        return None

    inferred_units: set[str] = set()
    for row in table.rows:
        for life_value, salvage_value, annual_rate_value in (
            (row.current_useful_life, row.current_salvage_rate, row.current_annual_rate),
            (row.prior_useful_life, row.prior_salvage_rate, row.prior_annual_rate),
        ):
            candidates = _life_units_consistent_with_annual_rate(
                life_value,
                salvage_value,
                annual_rate_value,
            )
            if len(candidates) == 1:
                inferred_units.update(candidates)
    return next(iter(inferred_units)) if len(inferred_units) == 1 else None


def _life_units_consistent_with_annual_rate(
    life_value: object,
    salvage_value: object,
    annual_rate_value: object,
) -> set[str]:
    """Infer an unlabeled life unit only when straight-line inputs uniquely support it."""
    salvage = parse_rate_range(salvage_value)
    annual_rate = parse_rate_range(annual_rate_value)
    if is_blank(life_value) or salvage is None or annual_rate is None:
        return set()

    candidates: set[str] = set()
    for unit in ("year", "month"):
        life = parse_life_range(life_value, assume_number_unit=unit)
        if life is None or life.min_months <= 0:
            continue
        min_years = life.min_months / Decimal("12")
        max_years = life.max_months / Decimal("12")
        expected_min = (Decimal("1") - salvage.max_rate) / max_years
        expected_max = (Decimal("1") - salvage.min_rate) / min_years
        if (
            abs(annual_rate.min_rate - expected_min) <= _LIFE_UNIT_RATE_TOL
            and abs(annual_rate.max_rate - expected_max) <= _LIFE_UNIT_RATE_TOL
        ):
            candidates.add(unit)
    return candidates


def _policy_rows_by_category(table: object) -> dict[str, K03PolicyRow]:
    return {
        _category_key(row.asset_category): row
        for row in table.rows
        if _category_key(row.asset_category)
    }


def _has_comparable_fa_life(table: object, fa_list: FaListDataset) -> bool:
    unit = _infer_policy_life_unit(table)
    policy_by_category = _policy_rows_by_category(table)
    for record in fa_list.records:
        policy = policy_by_category.get(_category_key(record.asset_category))
        if policy is None:
            continue
        if (
            parse_life_range(policy.current_useful_life, assume_number_unit=unit) is not None
            and parse_life_range(record.useful_life_months, assume_number_unit="month") is not None
        ):
            return True
    return False


def _has_comparable_fa_salvage(table: object, fa_list: FaListDataset) -> bool:
    policy_by_category = _policy_rows_by_category(table)
    for record in fa_list.records:
        policy = policy_by_category.get(_category_key(record.asset_category))
        if policy is None:
            continue
        if parse_rate_range(policy.current_salvage_rate) is not None and parse_rate(record.salvage_rate) is not None:
            return True
    return False


def _marker_is_true(value: object) -> bool:
    text = _norm_text(value)
    return text in {"true", "yes", "y", "1", "是", "一致", "无差异", "无变化"}


def _has_valid_note(dataset: K03SheetDataset) -> bool:
    return bool(dataset.note_area and _has_valid_explanation(dataset.note_area.text))


def _has_valid_explanation(value: object) -> bool:
    if is_blank(value):
        return False
    text = _norm_text(value)
    return text not in _PLACEHOLDERS and len(text) > 1


def _category_key(value: object) -> str:
    return _norm_text(value).replace("固定资产", "")


def _norm_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"[\s_\-，,。；;：:（）()\[\]【】]+", "", str(value).strip().lower())


def _policy_row_issue(
    dataset: K03SheetDataset,
    row: K03PolicyRow,
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
) -> QcIssue:
    cell = row.cell_refs.get(field)
    if cell:
        message = f"{message} 单元格={cell}。"
    return _issue(
        dataset,
        rule_id,
        field,
        severity,
        message,
        suggestion,
        source_row=row.source_row,
        source_col=_cell_col(cell),
    )


def _issue(
    dataset: K03SheetDataset,
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    *,
    source_row: int | None = None,
    source_col: int | None = None,
    source_sheet: str | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=rule_id,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.03.3",
        source_sheet=source_sheet or dataset.sheet_name,
        source_row=source_row,
        source_col=source_col,
    )
