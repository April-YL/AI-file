from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalReconciliationMatrix,
    DisposalSampleOutputDataset,
    DisposalTestSheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.models import AssetRecord
from ingest.records import DisposalListSummary, FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.disposal_consistency import build_disposal_consistency_preview
from rules.lead_common import field_values
from rules.models import QcIssue
from rules.parsing import parse_amount

_MEASURES = ("original_value", "accumulated_depreciation", "impairment_provision", "net_value")


def build_disposal_reconciliation_readability_observation(
    disposal_test: DisposalTestSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    matrix = disposal_test.reconciliation_matrix if disposal_test else None
    return _observation(
        checked_data=[_matrix_item(disposal_test, matrix)],
        check_logic="读取 K.02.2 处置测试页的总体核对矩阵，检查是否能识别金额列、处置清单行、Breakdown 行、差异行和调查行。",
        expected_result="K.02.2 应能稳定定位总体核对矩阵，并具备继续执行金额勾稽规则所需的行列结构。",
        actual_result=(
            f"识别到总体核对矩阵：{'是' if matrix else '否'}；"
            f"可执行确定性规则：{'是' if matrix and matrix.usable_for_rules else '否'}；"
            f"缺失组件 {len(matrix.missing_components) if matrix else 1} 项。"
        ),
        result_summary=_result_summary(issues),
    )


def build_disposal_reconciliation_formula_source_observation(
    disposal_test: DisposalTestSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    matrix = disposal_test.reconciliation_matrix if disposal_test else None
    return _observation(
        checked_data=[_matrix_item(disposal_test, matrix, include_values=True)],
        check_logic="读取总体核对矩阵中处置清单行和 Breakdown 行的公式来源，检查公式是否引用预期的处置清单和 K.01 后推表。",
        expected_result="处置清单行应引用处置清单；Breakdown 行应引用 K.01 后推表或等价来源。",
        actual_result=f"本次读取核对矩阵公式来源，公式来源异常 finding {len(issues)} 条。",
        result_summary=_result_summary(issues),
    )


def build_disposal_net_value_recalculation_observation(
    disposal_test: DisposalTestSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    matrix = disposal_test.reconciliation_matrix if disposal_test else None
    return _observation(
        checked_data=[_matrix_item(disposal_test, matrix, include_values=True)],
        check_logic="读取总体核对矩阵各行的原值、累计折旧、减值准备和净值，重新计算净值是否等于原值减累计折旧减减值准备。",
        expected_result="处置清单行、Breakdown 行和差异行的净值计算关系应成立。",
        actual_result=f"本次检查矩阵净值重算关系，净值重算异常 finding {len(issues)} 条。",
        result_summary=_result_summary(issues),
    )


def build_disposal_rollforward_reconciliation_observation(
    disposal_list_summary: DisposalListSummary | None,
    disposal_test: DisposalTestSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    matrix = disposal_test.reconciliation_matrix if disposal_test else None
    return _observation(
        checked_data=[
            _summary_item(disposal_list_summary),
            _matrix_item(disposal_test, matrix, include_values=True),
            _rollforward_item(rollforward),
            _lead_item(lead, "SAD", field_values(lead).get("sad") if lead else None),
        ],
        check_logic="读取处置清单汇总、K.02.2 总体核对矩阵、K.01 后推处置金额和 Lead SAD，用于展示处置总体金额勾稽过程。",
        expected_result="处置清单出售/报废总体、K.02.2 矩阵、K.01 后推处置行应在原值、累计折旧、减值准备和净值口径上保持一致；差异超过 SAD 时应提示复核。",
        actual_result=f"本次执行处置总体勾稽，勾稽 finding {len(issues)} 条。",
        result_summary=_result_summary(issues),
    )


def build_disposal_required_fields_observation(
    disposal_list: FaListDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    issue_rows = _issue_rows(issues)
    return _observation(
        checked_data=[
            _list_item(
                disposal_list,
                section="K.02.2 处置清单必填字段",
                key_columns=[
                    "asset_category",
                    "asset_id",
                    "asset_name",
                    "original_value",
                    "accumulated_depreciation",
                    "impairment_provision",
                    "disposal_date",
                    "disposal_method",
                ],
                rows=issue_rows or _sample_rows(disposal_list),
                values_read=_record_values(disposal_list, issue_rows or _sample_rows(disposal_list)),
                missing_data=[] if disposal_list else ["处置清单"],
            )
        ],
        check_logic="读取处置清单字段映射和资产明细，检查处置测试所需字段是否存在，并检查已识别字段是否存在空值。",
        expected_result="处置清单应包含资产类别、编号、名称、原值、累计折旧、减值准备、处置日期和处置方式等关键字段。",
        actual_result=f"本次读取处置清单 {len(disposal_list.records) if disposal_list else 0} 行，必填字段 finding {len(issues)} 条。",
        result_summary=_result_summary(issues),
    )


def build_disposal_list_net_value_observation(
    disposal_list: FaListDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    rows = _issue_rows(issues) or _sample_rows(disposal_list)
    return _observation(
        checked_data=[
            _list_item(
                disposal_list,
                section="K.02.2 处置清单净值重算",
                key_columns=list(_MEASURES),
                rows=rows,
                values_read=_record_values(disposal_list, rows, fields=list(_MEASURES)),
                missing_data=[] if disposal_list else ["处置清单"],
            )
        ],
        check_logic="逐行读取处置清单原值、累计折旧、减值准备和净值，重新计算净值是否等于原值减累计折旧减减值准备。",
        expected_result="处置清单每行净值应与按原值、累计折旧和减值准备重算的金额一致。",
        actual_result=f"本次执行处置清单净值重算，净值异常 finding {len(issues)} 条。",
        result_summary=_result_summary(issues),
    )


def build_disposal_sample_pool_observation(
    disposal_list_summary: DisposalListSummary | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    item = disposal_sample_output.amounts.get("sample_pool_amount") if disposal_sample_output else None
    return _observation(
        checked_data=[
            _sample_output_amount_item(disposal_sample_output, keys=["sample_pool_amount"]),
            _summary_item(disposal_list_summary),
        ],
        check_logic="读取 K.02.2a 样本池总体金额，并与处置清单出售/报废净值总体进行核对。",
        expected_result="K.02.2a 样本池金额应与处置清单中出售/报废总体净值一致，不应混入其他减少项目。",
        actual_result=(
            f"K.02.2a样本池金额={_text(item.amount if item else None)}；"
            f"处置清单出售/报废净值={_text(disposal_list_summary.sale_scrap_net_value if disposal_list_summary else None)}；"
            f"finding {len(issues)} 条。"
        ),
        result_summary=_result_summary(issues),
    )


def build_disposal_sample_match_observation(
    disposal_test: DisposalTestSheetDataset | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
    execution_path: DisposalExecutionPathDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    preview = build_disposal_consistency_preview(
        disposal_test,
        disposal_sample_output,
        execution_path=execution_path,
    )
    return _observation(
        checked_data=[
            _execution_path_item(execution_path),
            _sample_rows_item(disposal_sample_output),
            _tested_rows_item(disposal_test),
        ],
        check_logic="读取 K.02.2a 已选处置样本和 K.02.2 实际测试样本，按资产编号匹配，并展示样本类型和净值是否一致。",
        expected_result="K.02.2a 已选样本应进入 K.02.2 实际测试页；同一资产的样本类型和净值口径应保持一致。",
        actual_result=(
            f"已选样本 {preview.selected_count} 条，测试样本 {preview.tested_count} 条，"
            f"匹配 {preview.matched_count} 条，未匹配已选样本 {len(preview.unmatched_selected)} 条。"
        ),
        result_summary=_result_summary(issues),
    )


def build_disposal_data_insufficient_observation(rule_id: str, reason: str) -> dict:
    return _observation(
        checked_data=[
            {
                "sheet": None,
                "section": _rule_section(rule_id),
                "location": None,
                "identified_by": {
                    "sheet_name": None,
                    "section": _rule_section(rule_id),
                    "matched_keywords": [],
                    "matched_rows": [],
                    "matched_columns": [],
                },
                "key_columns": [],
                "values_read": [],
                "missing_data": [reason],
            }
        ],
        check_logic="本规则依赖 K.02.2 处置测试资料；资料不足时只记录未执行原因，不读取或推断底稿数值。",
        expected_result="应先识别到规则所需资料后，再执行处置测试相关检查。",
        actual_result=f"本次未执行该规则：{reason}",
        result_summary="资料不足，未执行本规则。",
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


def _matrix_item(
    disposal_test: DisposalTestSheetDataset | None,
    matrix: DisposalReconciliationMatrix | None,
    *,
    include_values: bool = False,
) -> dict:
    rows = [row.source_row for row in matrix.rows.values()] if matrix else []
    return {
        "sheet": disposal_test.source_sheet if disposal_test else None,
        "section": "K.02.2 总体核对矩阵",
        "location": _location([matrix.header_row if matrix else None, *rows]),
        "identified_by": {
            "sheet_name": disposal_test.source_sheet if disposal_test else None,
            "section": "reconciliation_matrix",
            "matched_keywords": list(matrix.recognition_evidence[:8]) if matrix else [],
            "matched_rows": _clean_ints([matrix.header_row if matrix else None, *rows]),
            "matched_columns": list((matrix.measure_columns.values() if matrix else []))[:12],
        },
        "key_columns": list(_MEASURES),
        "values_read": _matrix_values(matrix) if include_values else [
            _value_read("识别置信度", matrix.recognition_confidence if matrix else None, amount_type="ingest"),
            _value_read("可执行确定性规则", "是" if matrix and matrix.usable_for_rules else "否", amount_type="ingest_status"),
        ],
        "missing_data": list(matrix.missing_components[:12]) if matrix else ["K.02.2 总体核对矩阵"],
    }


def _summary_item(summary: DisposalListSummary | None) -> dict:
    return {
        "sheet": summary.source_sheet if summary else None,
        "section": "处置清单汇总",
        "location": None,
        "identified_by": {
            "sheet_name": summary.source_sheet if summary else None,
            "section": "disposal_list_summary",
            "matched_keywords": ["出售", "报废", "其他减少"],
            "matched_rows": [],
            "matched_columns": [],
        },
        "key_columns": ["sale_scrap_net_value", "other_reduction_net_value", "total_net_value"],
        "values_read": [
            _value_read("出售/报废净值", summary.sale_scrap_net_value, amount_type="处置清单汇总"),
            _value_read("其他减少净值", summary.other_reduction_net_value, amount_type="处置清单汇总"),
            _value_read("总净值", summary.total_net_value, amount_type="处置清单汇总"),
        ] if summary else [],
        "missing_data": [] if summary else ["处置清单汇总"],
    }


def _rollforward_item(rollforward: RollforwardSheetDataset | None) -> dict:
    values = []
    rows = []
    for measure in _MEASURES:
        amount, row = get_movement_transaction_amount(
            rollforward,
            transaction_key="disposal",
            measure=measure,
        )
        values.append(_value_read(f"K.01处置{measure}", amount, row=row, amount_type="K.01后推金额"))
        rows.append(row)
    return {
        "sheet": rollforward.source_sheet if rollforward else None,
        "section": "K.01 后推处置金额",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": rollforward.source_sheet if rollforward else None,
            "section": "movement_transactions",
            "matched_keywords": ["处置", "报废", "disposal"],
            "matched_rows": _clean_ints(rows),
            "matched_columns": [],
        },
        "key_columns": list(_MEASURES),
        "values_read": values,
        "missing_data": [] if rollforward else ["K.01 后推表"],
    }


def _lead_item(lead: LeadSheetDataset | None, label: str, value: object | None) -> dict:
    fields = [
        field
        for field in (lead.basic_info_fields if lead else [])
        if field.field_key.lower() == label.lower() or field.label == label
    ]
    return {
        "sheet": lead.source_sheet if lead else None,
        "section": f"K.00 Lead {label}",
        "location": _location([field.source_row for field in fields]),
        "identified_by": {
            "sheet_name": lead.source_sheet if lead else None,
            "section": "basic_info",
            "matched_keywords": [label],
            "matched_rows": _clean_ints([field.source_row for field in fields]),
            "matched_columns": _clean_ints([field.source_col for field in fields]),
        },
        "key_columns": [label.lower()],
        "values_read": [
            _value_read(label, value, row=fields[0].source_row if fields else None, column=fields[0].source_col if fields else None, amount_type="Lead参数")
        ] if value is not None else [],
        "missing_data": [] if value is not None else [f"Lead {label}"],
    }


def _list_item(
    disposal_list: FaListDataset | None,
    *,
    section: str,
    key_columns: list[str],
    rows: list[int | None],
    values_read: list[dict],
    missing_data: list[str],
) -> dict:
    mapped = {m.standard_field: m for m in disposal_list.mapped_fields} if disposal_list else {}
    return {
        "sheet": disposal_list.source_sheet if disposal_list else None,
        "section": section,
        "location": _location(rows),
        "identified_by": {
            "sheet_name": disposal_list.source_sheet if disposal_list else None,
            "section": section,
            "matched_keywords": [mapped[field].source_header for field in key_columns if field in mapped],
            "matched_rows": _clean_ints(rows),
            "matched_columns": [mapped[field].column_index for field in key_columns if field in mapped],
        },
        "key_columns": key_columns,
        "values_read": values_read,
        "missing_data": missing_data,
    }


def _sample_output_amount_item(
    sample_output: DisposalSampleOutputDataset | None,
    *,
    keys: list[str],
) -> dict:
    amounts = sample_output.amounts if sample_output else {}
    rows = [amounts[key].source_row for key in keys if key in amounts]
    columns = [amounts[key].source_column for key in keys if key in amounts and amounts[key].source_column]
    return {
        "sheet": sample_output.source_sheet if sample_output else None,
        "section": "K.02.2a 选样输出金额",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": sample_output.source_sheet if sample_output else None,
            "section": "amounts",
            "matched_keywords": [amounts[key].label for key in keys if key in amounts],
            "matched_rows": _clean_ints(rows),
            "matched_columns": columns,
        },
        "key_columns": keys,
        "values_read": [
            _value_read(amounts[key].label, amounts[key].amount, row=amounts[key].source_row, column=amounts[key].source_column, amount_type="K.02.2a金额")
            for key in keys
            if key in amounts
        ],
        "missing_data": [key for key in keys if key not in amounts],
    }


def _execution_path_item(path: DisposalExecutionPathDataset | None) -> dict:
    return {
        "sheet": None,
        "section": "K.02.2 执行路径识别",
        "location": _location([path.summary_source_row] if path else []),
        "identified_by": {
            "sheet_name": None,
            "section": "execution_path",
            "matched_keywords": [path.path_kind] if path else [],
            "matched_rows": [path.summary_source_row] if path and path.summary_source_row else [],
            "matched_columns": [],
        },
        "key_columns": ["path_kind", "disposal_list_sheet", "disposal_test_sheet", "disposal_sample_output_sheet"],
        "values_read": [
            _value_read("执行路径", path.path_kind, amount_type="ingest"),
            _value_read("识别置信度", path.recognition_confidence, amount_type="ingest"),
        ] if path else [],
        "missing_data": [] if path else ["K.02.2 执行路径识别结果"],
    }


def _sample_rows_item(sample_output: DisposalSampleOutputDataset | None) -> dict:
    rows = [row.source_row for row in (sample_output.selected_samples if sample_output else [])[:5]]
    return {
        "sheet": sample_output.source_sheet if sample_output else None,
        "section": "K.02.2a 已选处置样本",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": sample_output.source_sheet if sample_output else None,
            "section": "selected_samples",
            "matched_keywords": ["已选样本", "资产编号", "净值", "样本类型"],
            "matched_rows": _clean_ints(rows),
            "matched_columns": [],
        },
        "key_columns": ["sample_type", "asset_id", "asset_name", "net_value"],
        "values_read": _sample_values(sample_output),
        "missing_data": [] if sample_output else ["K.02.2a 处置选样输出"],
    }


def _tested_rows_item(disposal_test: DisposalTestSheetDataset | None) -> dict:
    rows = [row.source_row for row in (disposal_test.tested_samples if disposal_test else [])[:5]]
    return {
        "sheet": disposal_test.source_sheet if disposal_test else None,
        "section": "K.02.2 实际测试样本",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": disposal_test.source_sheet if disposal_test else None,
            "section": "tested_samples",
            "matched_keywords": ["测试样本", "资产编号", "净值", "处置方式"],
            "matched_rows": _clean_ints(rows),
            "matched_columns": [],
        },
        "key_columns": ["sample_type", "asset_id", "asset_name", "net_value", "disposal_method"],
        "values_read": _tested_values(disposal_test),
        "missing_data": [] if disposal_test else ["K.02.2 处置测试"],
    }


def _matrix_values(matrix: DisposalReconciliationMatrix | None) -> list[dict]:
    values = []
    if matrix is None:
        return values
    for row_key, row in list(matrix.rows.items())[:4]:
        for measure in _MEASURES:
            cell = row.measures.get(measure)
            if cell is None:
                continue
            values.append(
                _value_read(
                    f"{row_key}.{measure}",
                    cell.value,
                    row=cell.source_row,
                    column=cell.source_column,
                    amount_type="K.02.2核对矩阵",
                )
            )
    return values[:20]


def _record_values(
    disposal_list: FaListDataset | None,
    rows: list[int | None],
    *,
    fields: list[str] | None = None,
) -> list[dict]:
    if disposal_list is None:
        return []
    wanted = set(_clean_ints(rows)) or {record.source_row for record in disposal_list.records[:3]}
    fields = fields or [
        "asset_id",
        "asset_name",
        "original_value",
        "accumulated_depreciation",
        "impairment_provision",
        "net_value",
        "disposal_method",
    ]
    values = []
    for record in disposal_list.records:
        if record.source_row not in wanted:
            continue
        for field in fields:
            values.append(_value_read(field, getattr(record, field, None), row=record.source_row, amount_type="处置清单字段"))
    return values[:20]


def _sample_values(sample_output: DisposalSampleOutputDataset | None) -> list[dict]:
    values = []
    for row in (sample_output.selected_samples if sample_output else [])[:5]:
        values.extend(
            [
                _value_read("样本类型", row.sample_type, row=row.source_row, amount_type="K.02.2a样本"),
                _value_read("资产编号", row.asset_id, row=row.source_row, amount_type="K.02.2a样本"),
                _value_read("净值", row.net_value, row=row.source_row, amount_type="K.02.2a样本"),
            ]
        )
    return values[:20]


def _tested_values(disposal_test: DisposalTestSheetDataset | None) -> list[dict]:
    values = []
    for row in (disposal_test.tested_samples if disposal_test else [])[:5]:
        values.extend(
            [
                _value_read("样本类型", row.sample_type, row=row.source_row, amount_type="K.02.2测试样本"),
                _value_read("资产编号", row.asset_id, row=row.source_row, amount_type="K.02.2测试样本"),
                _value_read("净值", row.net_value, row=row.source_row, amount_type="K.02.2测试样本"),
                _value_read("处置方式", row.disposal_method, row=row.source_row, amount_type="K.02.2测试样本"),
            ]
        )
    return values[:20]


def _issue_rows(issues: list[QcIssue]) -> list[int | None]:
    return sorted({issue.source_row for issue in issues if issue.source_row is not None})


def _sample_rows(disposal_list: FaListDataset | None) -> list[int | None]:
    return [record.source_row for record in (disposal_list.records if disposal_list else [])[:3]]


def _result_summary(issues: list[QcIssue]) -> str:
    return f"触发 finding {len(issues)} 条。" if issues else "未触发 finding。"


def _rule_section(rule_id: str) -> str:
    return {
        "disposal_reconciliation_formula_source": "K.02.2 总体核对矩阵公式来源",
        "disposal_net_value_recalculation": "K.02.2 总体核对矩阵净值重算",
        "disposal_rollforward_reconciliation": "K.02.2 总体金额勾稽",
        "disposal_required_fields": "K.02.2 处置清单必填字段",
        "disposal_list_net_value_recalculation": "K.02.2 处置清单净值重算",
        "disposal_sample_pool_amount_match": "K.02.2a 样本池金额",
        "disposal_sample_match": "K.02.2 样本一致性",
    }.get(rule_id, "K.02.2 处置测试")


def _value_read(
    label: str,
    value: object | None,
    *,
    row: int | None = None,
    column: int | None = None,
    unit: str | None = None,
    amount_type: str | None = None,
) -> dict:
    return {
        "label": label,
        "value": _json_value(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": unit,
        "amount_type": amount_type,
    }


def _location(rows: list[int | None]) -> str | None:
    clean = _clean_ints(rows)
    if not clean:
        return None
    if len(clean) == 1:
        return f"row {clean[0]}"
    return f"rows {min(clean)}-{max(clean)}"


def _clean_ints(values: Iterable[int | None]) -> list[int]:
    return sorted({int(value) for value in values if value is not None})


def _cell(row: int | None, column: int | None) -> str | None:
    if row is None or column is None:
        return None
    return f"{_column_letter(column)}{row}"


def _column_letter(column: int) -> str:
    result = ""
    current = int(column)
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _json_value(value: object | None) -> object | None:
    if isinstance(value, Decimal):
        return str(value)
    parsed = parse_amount(str(value)) if value not in (None, "") else None
    if parsed is not None and str(value).replace(",", "").replace(".", "").replace("-", "").isdigit():
        return str(parsed)
    return value


def _text(value: object | None) -> str:
    if value is None or value == "":
        return "未记录"
    return str(value)
