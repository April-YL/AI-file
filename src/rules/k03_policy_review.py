from __future__ import annotations

import re
from dataclasses import dataclass
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
    "k03_policy_sheet_missing",
    "k03_policy_table_unreadable",
    "k03_policy_sections_incomplete",
    "k03_policy_difference_marker",
    "k03_policy_change_without_explanation",
    "k03_policy_fa_life_out_of_range",
    "k03_policy_fa_salvage_mismatch",
    "k03_policy_fa_unit_or_category_review",
    "k03_policy_obvious_anomaly",
)

_MAX_DETAIL_FINDINGS = 5
_RATE_TOL = Decimal("0.0001")
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


def run_k03_policy_review_rules(
    dataset: K03SheetDataset | None,
    *,
    fa_list: FaListDataset | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
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
            ("k03_policy_sheet_missing",),
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
            ("k03_policy_table_unreadable",),
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
        observation = None
        if rule_id in K03_LOW_RISK_HOW_RULE_IDS:
            observation = build_k03_policy_low_risk_observation(
                rule_id,
                dataset,
                issues,
                fa_list=fa_list,
            )
        recorder.record_executed(rule_id, counts.get(rule_id, 0), observation=observation)


def _check_structure(dataset: K03SheetDataset) -> list[QcIssue]:
    table = dataset.policy_table
    if table is None:
        return []
    fields = set(table.column_map)
    issues: list[QcIssue] = []
    required_groups = {
        "current_policy": {"current_useful_life", "current_salvage_rate"},
        "prior_policy": {"prior_useful_life", "prior_salvage_rate"},
        "difference_area": {"useful_life_same_marker", "salvage_rate_same_marker", "difference_explanation"},
    }
    for group, candidates in required_groups.items():
        if not (fields & candidates):
            issues.append(
                _issue(
                    dataset,
                    "k03_policy_sections_incomplete",
                    group,
                    Severity.NEED_REVIEW,
                    f"K.03.3 折旧政策表缺少或无法映射 {group} 相关栏目。",
                    "请确认表 1 是否完整列示本期政策、上期政策和差异判断/说明区。",
                    source_row=table.header_row,
                )
            )
    if dataset.note_area is None:
        issues.append(
            _issue(
                dataset,
                "k03_policy_sections_incomplete",
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
    issues: list[QcIssue] = []
    for row in dataset.policy_table.rows:
        changed_fields = _changed_policy_fields(row)
        same_fields = _same_policy_fields(row)
        issues.extend(_check_policy_anomalies(dataset, row))

        if "useful_life" in same_fields and not _marker_is_true(row.useful_life_same_marker):
            issues.append(
                _policy_row_issue(
                    dataset,
                    row,
                    "k03_policy_difference_marker",
                    "useful_life_same_marker",
                    Severity.WARN,
                    "本期与上期使用寿命看起来一致，但差异标记未显示为 TRUE 或等同含义。",
                    "请检查使用寿命差异公式或标记是否正确。",
                )
            )
        if "salvage_rate" in same_fields and not _marker_is_true(row.salvage_rate_same_marker):
            issues.append(
                _policy_row_issue(
                    dataset,
                    row,
                    "k03_policy_difference_marker",
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
                    "k03_policy_difference_marker",
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
                    "k03_policy_difference_marker",
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
                    "k03_policy_change_without_explanation",
                    "difference_explanation",
                    Severity.FAIL,
                    "本期与上期折旧政策存在差异，但未识别到有效差异说明或 Notes。",
                    "请针对折旧政策变化补充差异说明或 Notes，说明原因和处理结论。",
                )
            )
    return issues


def _check_fa_list_consistency(
    dataset: K03SheetDataset,
    fa_list: FaListDataset | None,
) -> list[QcIssue]:
    if fa_list is None or not fa_list.records:
        return [
            _issue(
                dataset,
                "k03_policy_fa_unit_or_category_review",
                "fa_list",
                Severity.NEED_REVIEW,
                "未取得可用于与 K.03.3 折旧政策表比对的 FA list。",
                "请确认 FA list 工作表及资产类别、使用寿命、残值率字段是否已正确识别。",
            )
        ]
    if dataset.policy_table is None:
        return []

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
            category_review_count += 1
            continue
        policy = policy_by_category.get(category_key)
        if policy is None:
            category_review_count += 1
            continue

        life_issue = _fa_life_issue(dataset, fa_list, rec, policy)
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

        for anomaly in _fa_anomaly_issues(dataset, fa_list, rec):
            if anomaly_findings < _MAX_DETAIL_FINDINGS:
                issues.append(anomaly)
            anomaly_findings += 1

    if category_review_count:
        issues.append(
            _issue(
                dataset,
                "k03_policy_fa_unit_or_category_review",
                "asset_category",
                Severity.NEED_REVIEW,
                f"有 {category_review_count} 行 FA list 资产类别无法匹配到 K.03.3 折旧政策类别。",
                "请复核资产类别命名是否一致；如属于模板差异，后续可补充类别映射表。",
                source_sheet=fa_list.source_sheet,
            )
        )
    for count, rule_id, field in (
        (life_findings, "k03_policy_fa_life_out_of_range", "useful_life_months"),
        (salvage_findings, "k03_policy_fa_salvage_mismatch", "salvage_rate"),
        (anomaly_findings, "k03_policy_obvious_anomaly", "fa_list_anomaly"),
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


def _fa_life_issue(
    dataset: K03SheetDataset,
    fa_list: FaListDataset,
    rec: AssetRecord,
    policy: K03PolicyRow,
) -> QcIssue | None:
    policy_range = parse_life_range(policy.current_useful_life, assume_number_unit=None)
    asset_life = parse_life_range(rec.useful_life_months, assume_number_unit="month")
    if policy_range is None or asset_life is None:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_unit_or_category_review",
            field="useful_life_months",
            severity=Severity.NEED_REVIEW,
            message="无法解析使用寿命，不能完成 K.03.3 折旧政策与 FA list 的使用寿命比对。",
            suggestion="请确认使用寿命是按年还是按月列示，并检查该字段是否存在非标准格式。",
            procedure_code="K.03.3",
            source_sheet=fa_list.source_sheet,
            source_row=rec.source_row,
        )
    months = asset_life.min_months
    if months < policy_range.min_months or months > policy_range.max_months:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_life_out_of_range",
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
        )
    return None


def _fa_salvage_issue(
    dataset: K03SheetDataset,
    fa_list: FaListDataset,
    rec: AssetRecord,
    policy: K03PolicyRow,
) -> QcIssue | None:
    policy_rate = parse_rate(policy.current_salvage_rate)
    asset_rate = parse_rate(rec.salvage_rate)
    if policy_rate is None or asset_rate is None:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_unit_or_category_review",
            field="salvage_rate",
            severity=Severity.NEED_REVIEW,
            message="无法解析残值率，不能完成 K.03.3 折旧政策与 FA list 的残值率比对。",
            suggestion="请确认残值率是按百分比还是小数列示，并检查该字段是否存在非标准格式。",
            procedure_code="K.03.3",
            source_sheet=fa_list.source_sheet,
            source_row=rec.source_row,
        )
    if abs(policy_rate - asset_rate) > _RATE_TOL:
        return QcIssue(
            asset_id=rec.asset_id or rec.identity(),
            rule_id="k03_policy_fa_salvage_mismatch",
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


def _changed_policy_fields(row: K03PolicyRow) -> set[str]:
    changed: set[str] = set()
    current_life = parse_life_range(row.current_useful_life, assume_number_unit=None)
    prior_life = parse_life_range(row.prior_useful_life, assume_number_unit=None)
    if current_life and prior_life and current_life != prior_life:
        changed.add("useful_life")
    current_rate = parse_rate(row.current_salvage_rate)
    prior_rate = parse_rate(row.prior_salvage_rate)
    if current_rate is not None and prior_rate is not None and abs(current_rate - prior_rate) > _RATE_TOL:
        changed.add("salvage_rate")
    if _norm_text(row.current_method) and _norm_text(row.prior_method) and _norm_text(row.current_method) != _norm_text(row.prior_method):
        changed.add("method")
    if _norm_text(row.current_annual_rate) and _norm_text(row.prior_annual_rate) and _norm_text(row.current_annual_rate) != _norm_text(row.prior_annual_rate):
        changed.add("annual_rate")
    return changed


def _same_policy_fields(row: K03PolicyRow) -> set[str]:
    same: set[str] = set()
    current_life = parse_life_range(row.current_useful_life, assume_number_unit=None)
    prior_life = parse_life_range(row.prior_useful_life, assume_number_unit=None)
    if current_life and prior_life and current_life == prior_life:
        same.add("useful_life")
    current_rate = parse_rate(row.current_salvage_rate)
    prior_rate = parse_rate(row.prior_salvage_rate)
    if current_rate is not None and prior_rate is not None and abs(current_rate - prior_rate) <= _RATE_TOL:
        same.add("salvage_rate")
    return same


def _check_policy_anomalies(dataset: K03SheetDataset, row: K03PolicyRow) -> list[QcIssue]:
    issues: list[QcIssue] = []
    life = parse_life_range(row.current_useful_life, assume_number_unit=None)
    if is_blank(row.current_useful_life):
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.WARN, "折旧政策中的本期使用寿命为空。", "请补充本期使用寿命范围。"))
    elif life is None:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.NEED_REVIEW, "折旧政策中的本期使用寿命无法解析。", "请确认政策使用寿命是按年还是按月列示，并检查格式是否标准。"))
    elif life.min_months <= 0:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.FAIL, "折旧政策中的本期使用寿命为 0 或负数。", "请更正本期使用寿命。"))
    elif life.max_months > _EXTREME_LIFE_MONTHS:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.NEED_REVIEW, "折旧政策中的本期使用寿命异常偏高。", "请复核该政策寿命是否合理。"))

    rate = parse_rate(row.current_salvage_rate)
    if is_blank(row.current_salvage_rate):
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_salvage_rate", Severity.WARN, "折旧政策中的本期残值率为空。", "请补充本期残值率。"))
    elif rate is None or rate < 0 or rate > 1:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_salvage_rate", Severity.WARN, "折旧政策中的本期残值率无法解析或不在 0-100% 范围内。", "请更正本期残值率。"))
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
    if is_blank(value):
        return None
    text = str(value).strip().replace(",", "")
    has_percent = "%" in text or "％" in text
    text = text.replace("%", "").replace("％", "")
    try:
        amount = Decimal(re.sub(r"[^0-9.\-]", "", text))
    except (InvalidOperation, ValueError):
        return None
    if has_percent or abs(amount) > 1:
        amount = amount / Decimal("100")
    if amount < 0 or amount > 1:
        return None
    return amount


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
    )
