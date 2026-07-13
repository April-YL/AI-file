from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ingest.k03_sheet import K03DetailRow, K03SheetDataset, load_k03_detail_table
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.lead_common import field_values
from rules.models import QcIssue, Severity


K03_LOW_RISK_HOW_RULE_IDS: tuple[str, ...] = (
    "sap_precision_selection",
    "sap_te_consistency",
    "sap_high_cra_consistency",
    "sap_depreciation_difference",
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
    "k03_policy_sheet_missing",
    "k03_policy_table_unreadable",
    "k03_policy_sections_incomplete",
    "k03_tod_by_item_detail_unreadable",
    "k03_tod_by_item_required_fields",
    "k03_tod_by_item_sad_unavailable",
    "k03_tod_by_item_difference_column",
    "k03_tod_by_item_difference_over_sad",
    "k03_tod_by_item_total_difference_over_sad",
    "k03_tod_by_item_rollforward_depreciation",
    "k03_tod_by_item_conclusion_missing",
    "k03_policy_fa_life_out_of_range",
    "k03_policy_fa_salvage_mismatch",
    "k03_policy_fa_unit_or_category_review",
    "k03_policy_difference_marker",
    "k03_policy_change_without_explanation",
    "k03_policy_obvious_anomaly",
)


def build_k03_missing_dataset_observation(rule_id: str, *, reason: str) -> dict:
    return _observation(
        checked_data=[
            _checked_data(
                sheet=None,
                section="K.03 折旧测试 / 折旧政策复核",
                location=None,
                matched_keywords=[],
                matched_rows=[],
                matched_columns=[],
                key_columns=[],
                values_read=[],
                missing_data=[_missing_label(rule_id), reason],
            )
        ],
        check_logic="系统先识别是否存在 K.03 折旧测试或折旧政策复核资料；未识别到资料时，仅记录资料不足原因，不执行明细检查。",
        expected_result="底稿应包含可识别的 K.03 折旧测试或折旧政策复核工作表，才可继续执行相关规则。",
        actual_result=f"本次未取得可执行资料：{reason}",
        result_summary="资料不足，未触发 finding。",
    )


def build_k03_not_applicable_observation(
    rule_id: str,
    dataset: K03SheetDataset,
    *,
    reason: str,
) -> dict:
    return _observation(
        checked_data=[
            _dataset_item(
                dataset,
                section="K.03 执行路径识别",
                key_columns=["execution_path"],
                values_read=[
                    _value_read(
                        "识别到的执行路径",
                        dataset.execution_path,
                        row=None,
                        column=None,
                        amount_type="执行路径",
                    )
                ],
                missing_data=[reason],
            )
        ],
        check_logic="系统根据已识别的 K.03 执行路径判断本规则是否适用于当前工作表；不适用时不执行该规则。",
        expected_result="只有当前工作表属于规则对应的 K.03 执行路径时，才进入该规则检查。",
        actual_result=f"本次工作表不适用：{reason}",
        result_summary="本次不适用，未触发 finding。",
    )


def build_k03_tod_low_risk_observation(
    rule_id: str,
    dataset: K03SheetDataset,
    issues: Iterable[QcIssue],
    *,
    lead: LeadSheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
) -> dict:
    issues = list(issues)
    missing_data: list[str] = []
    values_read: list[dict] = []
    key_columns = _tod_key_columns(dataset)

    if rule_id == "k03_tod_by_item_detail_unreadable":
        if dataset.detail_table_ref is None:
            missing_data.append("K.03.2 by-item 明细表定位")
        elif not any(issue.rule_id == rule_id for issue in issues):
            values_read.extend(
                [
                    _value_read(
                        "明细表起始行",
                        dataset.detail_table_ref.start_row,
                        row=dataset.detail_table_ref.start_row,
                        column=dataset.detail_table_ref.start_col,
                        amount_type="资料定位",
                    ),
                    _value_read(
                        "明细表结束行",
                        dataset.detail_table_ref.end_row,
                        row=dataset.detail_table_ref.end_row,
                        column=dataset.detail_table_ref.end_col,
                        amount_type="资料定位",
                    ),
                ]
            )
        else:
            missing_data.append("K.03.2 by-item 明细行")
    elif rule_id == "k03_tod_by_item_required_fields":
        missing_data.extend(_missing_required_tod_fields(dataset))
        values_read.extend(_mapped_column_values(dataset))
    elif rule_id == "k03_tod_by_item_sad_unavailable":
        sad = _lead_value(lead, "sad")
        if sad in (None, ""):
            missing_data.append("K.00 Lead SAD")
        else:
            values_read.append(
                _value_read("K.00 Lead SAD", sad, row=None, column=None, amount_type="重要性金额")
            )

    elif rule_id in {
        "k03_tod_by_item_difference_column",
        "k03_tod_by_item_difference_over_sad",
        "k03_tod_by_item_total_difference_over_sad",
    }:
        values_read.extend(_tod_amount_values(dataset, issues, rule_id))
        if rule_id in {
            "k03_tod_by_item_difference_over_sad",
            "k03_tod_by_item_total_difference_over_sad",
        }:
            sad = _lead_value(lead, "sad")
            if sad in (None, ""):
                missing_data.append("K.00 Lead SAD")
            else:
                values_read.append(
                    _value_read("K.00 Lead SAD", sad, row=None, column=None, amount_type="materiality_amount")
                )
    elif rule_id == "k03_tod_by_item_rollforward_depreciation":
        values_read.extend(_tod_amount_values(dataset, issues, rule_id))
        rf_amount, rf_row = get_movement_transaction_amount(
            rollforward,
            transaction_key="depreciation",
            measure="accumulated_depreciation",
        )
        if rf_amount is None and rollforward is not None:
            rf_amount = rollforward.table4_rollforward_depreciation
            rf_row = rollforward.table4_rollforward_depreciation_row
        if rf_amount is None:
            missing_data.append("K.01 current period depreciation amount")
        else:
            values_read.append(
                _value_read("K.01 current period depreciation amount", rf_amount, row=rf_row, column=None, amount_type="depreciation_amount")
            )
    elif rule_id == "k03_tod_by_item_conclusion_missing":
        values_read.extend(_tod_explanation_values(dataset))
        if not values_read:
            missing_data.append("K.03.2 conclusion or explanation text")

    return _observation(
        checked_data=[
            _dataset_item(
                dataset,
                section=_tod_section(rule_id),
                key_columns=key_columns,
                values_read=values_read,
                missing_data=missing_data,
            )
        ],
        check_logic=_tod_logic(rule_id),
        expected_result=_tod_expected(rule_id),
        actual_result=_tod_actual(rule_id, dataset, issues, missing_data),
        result_summary=_result_summary(issues, rule_id),
    )


def build_k03_policy_low_risk_observation(
    rule_id: str,
    dataset: K03SheetDataset | None,
    issues: Iterable[QcIssue],
    *,
    fa_list: FaListDataset | None = None,
) -> dict:
    issues = list(issues)
    if dataset is None:
        return build_k03_missing_dataset_observation(
            rule_id,
            reason="未识别 K.03.3 折旧政策复核工作表",
        )

    table = dataset.policy_table
    key_columns = _policy_key_columns(dataset)
    missing_data: list[str] = []
    values_read: list[dict] = []
    if rule_id == "k03_policy_table_unreadable":
        if table is None or not table.rows:
            missing_data.append("K.03.3 折旧政策表 1")
        else:
            values_read.append(
                _value_read("政策表行数", len(table.rows), row=table.header_row, column=None, amount_type="资料读取")
            )
    elif rule_id == "k03_policy_sections_incomplete":
        missing_data.extend(_missing_policy_sections(dataset))
        values_read.extend(_policy_column_values(dataset))
    elif rule_id == "k03_policy_sheet_missing":
        values_read.append(
            _value_read("识别到的政策复核工作表", dataset.sheet_name, row=None, column=None, amount_type="资料识别")
        )

    elif rule_id in {
        "k03_policy_fa_life_out_of_range",
        "k03_policy_fa_salvage_mismatch",
        "k03_policy_fa_unit_or_category_review",
    }:
        values_read.extend(_policy_values(dataset, rule_id))
        values_read.extend(_fa_list_values(fa_list, issues, rule_id))
        if fa_list is None or not fa_list.records:
            missing_data.append("FA list")
    elif rule_id in {
        "k03_policy_difference_marker",
        "k03_policy_change_without_explanation",
        "k03_policy_obvious_anomaly",
    }:
        values_read.extend(_policy_values(dataset, rule_id))
        values_read.extend(_policy_note_values(dataset))
        if rule_id == "k03_policy_obvious_anomaly":
            values_read.extend(_fa_list_values(fa_list, issues, rule_id))
        if rule_id == "k03_policy_change_without_explanation" and not _policy_note_values(dataset):
            missing_data.append("K.03.3 difference explanation or Notes")

    return _observation(
        checked_data=[
            _dataset_item(
                dataset,
                section=_policy_section(rule_id),
                key_columns=key_columns,
                values_read=values_read,
                missing_data=missing_data,
            )
        ],
        check_logic=_policy_logic(rule_id),
        expected_result=_policy_expected(rule_id),
        actual_result=_policy_actual(rule_id, dataset, issues, missing_data),
        result_summary=_result_summary(issues, rule_id),
    )


def _observation(
    *,
    checked_data: list[dict],
    check_logic: str,
    expected_result: str,
    actual_result: str,
    result_summary: str,
) -> dict:
    return {
        "checked_data": checked_data,
        "check_logic": check_logic,
        "expected_result": expected_result,
        "actual_result": actual_result,
        "result_summary": result_summary,
    }


def _dataset_item(
    dataset: K03SheetDataset,
    *,
    section: str,
    key_columns: list[str],
    values_read: list[dict],
    missing_data: list[str],
) -> dict:
    rows = _dataset_rows(dataset)
    columns = _dataset_columns(dataset, key_columns)
    keywords = _dataset_keywords(dataset, key_columns)
    return _checked_data(
        sheet=dataset.sheet_name,
        section=section,
        location=_location(rows),
        matched_keywords=keywords,
        matched_rows=rows,
        matched_columns=columns,
        key_columns=key_columns,
        values_read=values_read,
        missing_data=missing_data,
    )


def _checked_data(
    *,
    sheet: str | None,
    section: str,
    location: str | None,
    matched_keywords: list[str],
    matched_rows: list[int],
    matched_columns: list[int],
    key_columns: list[str],
    values_read: list[dict],
    missing_data: list[str],
) -> dict:
    return {
        "sheet": sheet,
        "section": section,
        "location": location,
        "identified_by": {
            "sheet_name": sheet,
            "section": section,
            "matched_keywords": matched_keywords[:12],
            "matched_rows": matched_rows[:12],
            "matched_columns": matched_columns[:12],
        },
        "key_columns": key_columns[:12],
        "values_read": values_read[:20],
        "missing_data": [item for item in missing_data if item][:12],
    }


def _value_read(
    label: str,
    value: Any,
    *,
    row: int | None,
    column: int | None,
    amount_type: str,
) -> dict:
    return {
        "label": label,
        "value": _short_value(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": None,
        "amount_type": amount_type,
    }


def _short_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= 120:
        return text
    return text[:117] + "..."


def _tod_key_columns(dataset: K03SheetDataset) -> list[str]:
    fields = [
        "asset_id",
        "asset_name",
        "management_depreciation",
        "audit_recalculated_depreciation",
        "depreciation_difference",
    ]
    return [field for field in fields if field in dataset.normalized_column_map] or fields[:2]


def _policy_key_columns(dataset: K03SheetDataset) -> list[str]:
    table = dataset.policy_table
    if table is None:
        return ["asset_category", "current_useful_life", "current_salvage_rate"]
    return list(table.column_map)[:12]


def _mapped_column_values(dataset: K03SheetDataset) -> list[dict]:
    values: list[dict] = []
    for field, column in sorted(dataset.normalized_column_map.items()):
        values.append(
            _value_read(
                field,
                column.source_header,
                row=dataset.detail_table_ref.header_row if dataset.detail_table_ref else None,
                column=column.column_index,
                amount_type="字段映射",
            )
        )
    return values



def _tod_amount_values(
    dataset: K03SheetDataset,
    issues: list[QcIssue],
    rule_id: str,
) -> list[dict]:
    rows = _tod_rows(dataset, issues, rule_id)
    if rule_id == "k03_tod_by_item_rollforward_depreciation":
        fields = ["current_depreciation", "management_depreciation"]
    else:
        fields = [
            "management_depreciation",
            "audit_recalculated_depreciation",
            "depreciation_difference",
        ]
    values: list[dict] = []
    for row in rows:
        for field in fields:
            if field not in row.normalized_values:
                continue
            values.append(_detail_row_value(dataset, row, field, amount_type="depreciation_amount"))
    return values


def _tod_rows(
    dataset: K03SheetDataset,
    issues: list[QcIssue],
    rule_id: str,
) -> list[K03DetailRow]:
    table = load_k03_detail_table(dataset)
    candidates = (
        table.total_rows
        if rule_id == "k03_tod_by_item_total_difference_over_sad"
        else table.detail_rows
    )
    issue_rows = {issue.source_row for issue in _issues_for(issues, rule_id) if issue.source_row is not None}
    selected = [row for row in candidates if row.source_row in issue_rows]
    if not selected:
        selected = candidates[:3]
    return selected[:3]


def _detail_row_value(
    dataset: K03SheetDataset,
    row: K03DetailRow,
    field: str,
    *,
    amount_type: str,
) -> dict:
    column = dataset.normalized_column_map.get(field)
    return _value_read(
        field,
        row.normalized_values.get(field),
        row=row.source_row,
        column=column.column_index if column else None,
        amount_type=amount_type,
    )


def _tod_explanation_values(dataset: K03SheetDataset) -> list[dict]:
    values: list[dict] = []
    for label, area in (
        ("K.03.2 conclusion area", dataset.conclusion_area),
        ("K.03.2 note area", dataset.note_area),
    ):
        if area is None or not area.text:
            continue
        values.append(
            _value_read(
                label,
                area.text,
                row=area.start_row,
                column=area.start_col,
                amount_type="explanation_text",
            )
        )
    return values

def _policy_column_values(dataset: K03SheetDataset) -> list[dict]:
    table = dataset.policy_table
    if table is None:
        return []
    values: list[dict] = []
    for field, column in sorted(table.column_map.items()):
        values.append(
            _value_read(
                field,
                column.source_header,
                row=table.header_row,
                column=column.column_index,
                amount_type="字段映射",
            )
        )
    return values



def _policy_values(dataset: K03SheetDataset, rule_id: str) -> list[dict]:
    table = dataset.policy_table
    if table is None:
        return []
    fields = ["asset_category"]
    if rule_id in {"k03_policy_fa_life_out_of_range", "k03_policy_fa_unit_or_category_review"}:
        fields.append("current_useful_life")
    if rule_id in {"k03_policy_fa_salvage_mismatch", "k03_policy_fa_unit_or_category_review"}:
        fields.append("current_salvage_rate")
    if rule_id in {"k03_policy_difference_marker", "k03_policy_change_without_explanation"}:
        fields.extend(
            [
                "current_useful_life",
                "prior_useful_life",
                "current_salvage_rate",
                "prior_salvage_rate",
                "useful_life_same_marker",
                "salvage_rate_same_marker",
                "difference_explanation",
            ]
        )
    if rule_id == "k03_policy_obvious_anomaly":
        fields.extend(["current_useful_life", "current_salvage_rate"])
    fields = _dedupe_text(fields)
    values: list[dict] = []
    for row in table.rows[:3]:
        for field in fields:
            column = table.column_map.get(field)
            values.append(
                _value_read(
                    f"K.03.3 {field}",
                    getattr(row, field, None),
                    row=row.source_row,
                    column=column.column_index if column else None,
                    amount_type="depreciation_policy",
                )
            )
    return values


def _policy_note_values(dataset: K03SheetDataset) -> list[dict]:
    area = dataset.note_area
    if area is None or not area.text:
        return []
    return [
        _value_read(
            "K.03.3 Notes",
            area.text,
            row=area.start_row,
            column=area.start_col,
            amount_type="explanation_text",
        )
    ]


def _fa_list_values(
    fa_list: FaListDataset | None,
    issues: list[QcIssue],
    rule_id: str,
) -> list[dict]:
    if fa_list is None:
        return []
    issue_rows = {issue.source_row for issue in _issues_for(issues, rule_id) if issue.source_row is not None}
    records = [record for record in fa_list.records if record.source_row in issue_rows]
    if not records:
        records = fa_list.records[:3]
    fields = ["asset_category"]
    if rule_id in {"k03_policy_fa_life_out_of_range", "k03_policy_fa_unit_or_category_review"}:
        fields.append("useful_life_months")
    if rule_id in {"k03_policy_fa_salvage_mismatch", "k03_policy_fa_unit_or_category_review"}:
        fields.append("salvage_rate")
    values: list[dict] = []
    for record in records[:3]:
        for field in fields:
            values.append(
                _value_read(
                    f"FA list {field}",
                    getattr(record, field, None),
                    row=record.source_row,
                    column=_fa_list_column(fa_list, field),
                    amount_type="fa_list_field",
                )
            )
    return values


def _fa_list_column(fa_list: FaListDataset, field: str) -> int | None:
    for mapping in fa_list.mapped_fields:
        if mapping.standard_field == field:
            return getattr(mapping, "column_index", None) or getattr(mapping, "source_col", None)
    return None

def _missing_required_tod_fields(dataset: K03SheetDataset) -> list[str]:
    required = ["management_depreciation", "audit_recalculated_depreciation"]
    return [field for field in required if field not in dataset.normalized_column_map]


def _missing_policy_sections(dataset: K03SheetDataset) -> list[str]:
    table = dataset.policy_table
    if table is None:
        return ["K.03.3 折旧政策表 1"]
    fields = set(table.column_map)
    missing: list[str] = []
    groups = {
        "本期政策栏目": {"current_useful_life", "current_salvage_rate"},
        "上期政策栏目": {"prior_useful_life", "prior_salvage_rate"},
        "差异判断/说明栏目": {
            "useful_life_same_marker",
            "salvage_rate_same_marker",
            "difference_explanation",
        },
    }
    for label, candidates in groups.items():
        if not (fields & candidates):
            missing.append(label)
    if dataset.note_area is None:
        missing.append("Notes/说明区")
    return missing


def _dataset_rows(dataset: K03SheetDataset) -> list[int]:
    rows: list[int] = []
    if dataset.detail_table_ref and dataset.detail_table_ref.header_row:
        rows.append(dataset.detail_table_ref.header_row)
    if dataset.detail_table_range and dataset.detail_table_range.start_row:
        rows.append(dataset.detail_table_range.start_row)
    if dataset.policy_table and dataset.policy_table.header_row:
        rows.append(dataset.policy_table.header_row)
    if dataset.policy_table and dataset.policy_table.range and dataset.policy_table.range.start_row:
        rows.append(dataset.policy_table.range.start_row)
    if dataset.note_area and dataset.note_area.start_row:
        rows.append(dataset.note_area.start_row)
    return _dedupe_int(rows)


def _dataset_columns(dataset: K03SheetDataset, key_columns: list[str]) -> list[int]:
    values: list[int] = []
    for field in key_columns:
        column = dataset.normalized_column_map.get(field)
        if column:
            values.append(column.column_index)
        if dataset.policy_table:
            policy_col = dataset.policy_table.column_map.get(field)
            if policy_col:
                values.append(policy_col.column_index)
    return _dedupe_int(values)


def _dataset_keywords(dataset: K03SheetDataset, key_columns: list[str]) -> list[str]:
    keywords = [dataset.sheet_name]
    keywords.extend(dataset.detected_sections)
    for field in key_columns:
        column = dataset.normalized_column_map.get(field)
        if column:
            keywords.append(column.source_header)
        if dataset.policy_table:
            policy_col = dataset.policy_table.column_map.get(field)
            if policy_col:
                keywords.append(policy_col.source_header)
    return _dedupe_text(keywords)


def _lead_value(lead: LeadSheetDataset | None, field: str) -> object | None:
    if lead is None:
        return None
    return field_values(lead).get(field)


def _tod_section(rule_id: str) -> str:
    if rule_id == "k03_tod_by_item_detail_unreadable":
        return "K.03.2 by-item 折旧测试明细表"
    if rule_id == "k03_tod_by_item_required_fields":
        return "K.03.2 by-item 折旧测试字段完整性"
    if rule_id == "k03_tod_by_item_sad_unavailable":
        return "K.03.2 by-item 折旧差异与 Lead SAD"
    return "K.03.2 by-item 折旧测试"


def _tod_logic(rule_id: str) -> str:
    if rule_id == "k03_tod_by_item_detail_unreadable":
        return "系统识别 K.03.2 by-item 折旧测试明细表位置，并尝试读取明细行；无法定位或无法读取明细行时记录资料不足。"
    if rule_id == "k03_tod_by_item_required_fields":
        return "系统读取 by-item 明细表表头，检查管理层折旧额和审计重新计算折旧额等核心字段是否可识别。"
    if rule_id == "k03_tod_by_item_sad_unavailable":
        return "系统在存在折旧差异时读取 K.00 Lead SAD，用于后续判断差异是否超过审计容忍水平；读取不到 SAD 时不作通过判断。"
    return "系统读取 K.03.2 by-item 折旧测试资料并记录执行证据。"


def _tod_expected(rule_id: str) -> str:
    if rule_id == "k03_tod_by_item_detail_unreadable":
        return "应能定位并读取 K.03.2 by-item 折旧测试明细表。"
    if rule_id == "k03_tod_by_item_required_fields":
        return "应能识别管理层折旧额和审计重新计算折旧额等核心折旧比对字段。"
    if rule_id == "k03_tod_by_item_sad_unavailable":
        return "如存在折旧差异，应能从 K.00 Lead 读取 SAD，作为后续差异判断依据。"
    return "应取得规则执行所需的 K.03.2 by-item 折旧测试资料。"


def _tod_actual(
    rule_id: str,
    dataset: K03SheetDataset,
    issues: list[QcIssue],
    missing_data: list[str],
) -> str:
    if rule_id == "k03_tod_by_item_detail_unreadable":
        if dataset.detail_table_ref is None:
            return "本次未能定位 K.03.2 by-item 明细表。"
        return f"本次识别到明细表范围，问题记录 {len(_issues_for(issues, rule_id))} 条。"
    if rule_id == "k03_tod_by_item_required_fields":
        return f"本次识别字段 {len(dataset.normalized_column_map)} 个，缺失核心字段 {len(missing_data)} 项。"
    if rule_id == "k03_tod_by_item_sad_unavailable":
        return f"本次 SAD 读取缺口 {len(missing_data)} 项，问题记录 {len(_issues_for(issues, rule_id))} 条。"
    return f"本次问题记录 {len(_issues_for(issues, rule_id))} 条。"


def _policy_section(rule_id: str) -> str:
    if rule_id == "k03_policy_sheet_missing":
        return "K.03.3 折旧政策复核工作表识别"
    if rule_id == "k03_policy_table_unreadable":
        return "K.03.3 折旧政策表读取"
    if rule_id == "k03_policy_sections_incomplete":
        return "K.03.3 折旧政策表结构完整性"
    return "K.03.3 折旧政策复核"


def _policy_logic(rule_id: str) -> str:
    if rule_id == "k03_policy_sheet_missing":
        return "系统识别是否存在 K.03.3 折旧政策复核工作表；未识别到时仅记录资料不足。"
    if rule_id == "k03_policy_table_unreadable":
        return "系统读取 K.03.3 折旧政策表 1，检查是否能取得政策类别和政策明细行。"
    if rule_id == "k03_policy_sections_incomplete":
        return "系统读取 K.03.3 政策表表头和说明区，检查本期政策、上期政策、差异判断/说明栏目是否可识别。"
    return "系统读取 K.03.3 折旧政策复核资料并记录执行证据。"


def _policy_expected(rule_id: str) -> str:
    if rule_id == "k03_policy_sheet_missing":
        return "底稿应包含可识别的 K.03.3 折旧政策复核工作表。"
    if rule_id == "k03_policy_table_unreadable":
        return "应能读取 K.03.3 折旧政策表 1 的表头和至少一行政策记录。"
    if rule_id == "k03_policy_sections_incomplete":
        return "政策表应包含本期政策、上期政策、差异判断/说明栏目，并尽量包含 Notes/说明区。"
    return "应取得规则执行所需的 K.03.3 折旧政策复核资料。"


def _policy_actual(
    rule_id: str,
    dataset: K03SheetDataset,
    issues: list[QcIssue],
    missing_data: list[str],
) -> str:
    if rule_id == "k03_policy_table_unreadable":
        row_count = len(dataset.policy_table.rows) if dataset.policy_table else 0
        return f"本次读取政策表记录 {row_count} 行，问题记录 {len(_issues_for(issues, rule_id))} 条。"
    if rule_id == "k03_policy_sections_incomplete":
        mapped = len(dataset.policy_table.column_map) if dataset.policy_table else 0
        return f"本次识别政策表字段 {mapped} 个，缺失资料区块 {len(missing_data)} 项。"
    if rule_id == "k03_policy_sheet_missing":
        return f"本次识别到工作表：{dataset.sheet_name}。"
    return f"本次问题记录 {len(_issues_for(issues, rule_id))} 条。"


def _missing_label(rule_id: str) -> str:
    if rule_id.startswith("sap_"):
        return "K.03.1 SAP 折旧测试工作表"
    if rule_id.startswith("depreciation_tod_"):
        return "K.03.2 TOD 抽样测试工作表"
    if rule_id.startswith("k03_policy_"):
        return "K.03.3 折旧政策复核工作表"
    return "K.03.2 by-item 折旧测试工作表"


def _result_summary(issues: list[QcIssue], rule_id: str) -> str:
    finding_count = sum(1 for issue in issues if issue.rule_id == rule_id and issue.severity != Severity.PASS)
    if finding_count:
        return f"触发 finding {finding_count} 条。"
    return "未触发 finding。"


def _issues_for(issues: list[QcIssue], rule_id: str) -> list[QcIssue]:
    return [issue for issue in issues if issue.rule_id == rule_id]


def _location(rows: list[int]) -> str | None:
    if not rows:
        return None
    return "行 " + ", ".join(str(row) for row in rows)


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


def _dedupe_int(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_text(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
