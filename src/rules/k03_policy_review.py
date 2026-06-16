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
) -> list[QcIssue]:
    if dataset is None:
        return [
            QcIssue(
                asset_id=None,
                rule_id="k03_policy_sheet_missing",
                field="sheet",
                severity=Severity.NEED_REVIEW,
                message="K.03.3 depreciation policy review sheet was not identified.",
                suggestion="Confirm whether the workbook includes K.03.3 depreciation policy review.",
                procedure_code="K.03.3",
                source_sheet="K.03.3 折旧政策复核",
            )
        ]
    if dataset.execution_path != EXECUTION_PATH_POLICY_REVIEW:
        return []

    issues: list[QcIssue] = []
    table = dataset.policy_table
    if table is None or not table.rows:
        return [
            _issue(
                dataset,
                "k03_policy_table_unreadable",
                "policy_table",
                Severity.NEED_REVIEW,
                "K.03.3 policy table 1 could not be identified or parsed.",
                "Check the policy review sheet for the asset category, current/prior policy, difference, and notes columns.",
            )
        ]

    issues.extend(_check_structure(dataset))
    issues.extend(_check_policy_rows(dataset))
    issues.extend(_check_fa_list_consistency(dataset, fa_list))
    return issues


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
                    f"K.03.3 policy table is missing or cannot map the {group} columns.",
                    "Confirm the table 1 current/prior policy columns and difference area.",
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
                "K.03.3 Notes area was not identified.",
                "If policy changes exist, document explanations in the difference explanation column or Notes area.",
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
                    "Current and prior useful life appear consistent, but the difference marker is not TRUE/equivalent.",
                    "Check the useful life difference formula or marker.",
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
                    "Current and prior salvage rate appear consistent, but the difference marker is not TRUE/equivalent.",
                    "Check the salvage rate difference formula or marker.",
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
                    "Useful life changed compared with prior period, but the difference marker remains TRUE.",
                    "Check whether the policy change has been identified correctly.",
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
                    "Salvage rate changed compared with prior period, but the difference marker remains TRUE.",
                    "Check whether the policy change has been identified correctly.",
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
                    "Current and prior depreciation policy differ, but no valid explanation or Notes were identified.",
                    "Add a difference explanation or Notes for the policy change.",
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
                "FA list was not available for comparison with K.03.3 policy table.",
                "Confirm the FA list sheet and mapped asset category, useful life, and salvage rate fields.",
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
                f"{category_review_count} FA list rows could not be matched to a K.03.3 policy category.",
                "Review asset category naming or add a category mapping table in a later phase.",
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
                    f"{count} FA list rows triggered {field} findings; only first {_MAX_DETAIL_FINDINGS} detail findings are shown.",
                    "Review all affected FA list rows for policy consistency.",
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
            message="Useful life could not be parsed for K.03.3 policy vs FA list comparison.",
            suggestion="Confirm whether useful life is expressed in years or months.",
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
                f"FA list useful life is outside K.03.3 policy range for category {rec.asset_category}: "
                f"asset={rec.useful_life_months}, policy={policy.current_useful_life}."
            ),
            suggestion="Check the FA list useful life or update the policy table explanation if the exception is valid.",
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
            message="Salvage rate could not be parsed for K.03.3 policy vs FA list comparison.",
            suggestion="Confirm whether salvage rate is expressed as a percentage or decimal.",
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
                f"FA list salvage rate differs from K.03.3 policy for category {rec.asset_category}: "
                f"asset={rec.salvage_rate}, policy={policy.current_salvage_rate}."
            ),
            suggestion="Check the FA list salvage rate or document why the asset uses a different rate.",
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
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list useful life is blank."))
    elif life is None:
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list useful life unit or format could not be parsed."))
    elif life.min_months <= 0:
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list useful life is zero or negative."))
    elif life.max_months > _EXTREME_LIFE_MONTHS:
        issues.append(_fa_anomaly(fa_list, rec, "useful_life_months", "FA list useful life is extremely high and needs review."))

    rate = parse_rate(rec.salvage_rate)
    if is_blank(rec.salvage_rate):
        issues.append(_fa_anomaly(fa_list, rec, "salvage_rate", "FA list salvage rate is blank."))
    elif rate is None:
        issues.append(_fa_anomaly(fa_list, rec, "salvage_rate", "FA list salvage rate could not be parsed or is outside 0-100%."))
    elif rate < 0 or rate > 1:
        issues.append(_fa_anomaly(fa_list, rec, "salvage_rate", "FA list salvage rate is outside 0-100%."))
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
        suggestion="Review the FA list value before applying detailed depreciation policy checks.",
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
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.WARN, "Policy useful life is blank.", "Fill in the current-period useful life range."))
    elif life is None:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.NEED_REVIEW, "Policy useful life could not be parsed.", "Confirm whether the policy useful life is expressed in years or months."))
    elif life.min_months <= 0:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.FAIL, "Policy useful life is zero or negative.", "Correct the current-period useful life."))
    elif life.max_months > _EXTREME_LIFE_MONTHS:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_useful_life", Severity.NEED_REVIEW, "Policy useful life is extremely high.", "Review whether this policy life is valid."))

    rate = parse_rate(row.current_salvage_rate)
    if is_blank(row.current_salvage_rate):
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_salvage_rate", Severity.WARN, "Policy salvage rate is blank.", "Fill in current-period salvage rate."))
    elif rate is None or rate < 0 or rate > 1:
        issues.append(_policy_row_issue(dataset, row, "k03_policy_obvious_anomaly", "current_salvage_rate", Severity.WARN, "Policy salvage rate is outside 0-100% or cannot be parsed.", "Correct the current-period salvage rate."))
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
        message = f"{message} Cell={cell}."
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
