from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from ingest.addition_test_sheet import (
    AdditionAmountItem,
    AdditionExecutionPathDataset,
    AdditionParameterItem,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.addition_common import sum_purchase_original_value
from rules.addition_consistency import build_addition_consistency_preview
from rules.lead_common import field_values
from rules.models import ColumnContext, QcIssue
from rules.parsing import parse_amount


def build_addition_required_fields_observation(
    addition_list: FaListDataset | None,
    ctx: ColumnContext | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    missing_columns = sorted({issue.field for issue in issues if issue.source_row is None and issue.field})
    blank_rows = sorted({issue.source_row for issue in issues if issue.source_row is not None})
    return _observation(
        checked_data=[
            _addition_list_item(
                addition_list,
                ctx,
                section="K.02.1 新增清单字段完整性",
                key_columns=[
                    "asset_id",
                    "asset_name",
                    "asset_category",
                    "start_date",
                    "original_value",
                    "addition_method",
                ],
                values_read=_record_values(addition_list, blank_rows),
                missing_data=missing_columns or ([] if addition_list else ["新增清单"]),
                rows=blank_rows,
            )
        ],
        check_logic="读取新增清单的字段映射和资产明细，检查新增测试所需的资产编号、名称、类别、入账日期、原值和新增方式是否可识别，并检查已识别字段是否存在空值。",
        expected_result="新增清单应包含并可读取新增测试所需字段；每条新增资产记录的关键字段不应为空。",
        actual_result=(
            f"本次读取新增清单 {len(addition_list.records) if addition_list else 0} 行，"
            f"字段缺失 {len(missing_columns)} 项，行级空值异常 {len(blank_rows)} 行。"
        ),
        result_summary=_result_summary(issues),
    )


def build_addition_population_homogeneity_observation(
    addition_list: FaListDataset | None,
    ctx: ColumnContext | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    issue_rows = _issue_rows(issues)
    rows = issue_rows or _sample_rows(addition_list)
    return _observation(
        checked_data=[
            _addition_list_item(
                addition_list,
                ctx,
                section="K.02.1 新增清单总体同质性",
                key_columns=["asset_id", "asset_name", "original_value", "addition_method"],
                values_read=_record_values(addition_list, rows, fields=["asset_id", "asset_name", "original_value", "addition_method"]),
                missing_data=[] if addition_list else ["新增清单"],
                rows=rows,
            )
        ],
        check_logic="读取新增清单中每条资产的新增方式，检查进入购置新增测试总体的记录是否存在非购置、非采购等不同性质的新增来源。",
        expected_result="购置新增测试总体应主要由购置/采购类新增构成；企业合并、调拨、重分类等不同性质项目应提示人工复核。",
        actual_result=f"本次读取新增清单 {len(addition_list.records) if addition_list else 0} 行，同质性提示 {len(issue_rows)} 行。",
        result_summary=_result_summary(issues),
    )


def build_addition_rollforward_reconciliation_observation(
    addition_list: FaListDataset | None,
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
    addition_test: AdditionTestSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    addition_total, _ = (
        sum_purchase_original_value(
            addition_list.records,
            {m.standard_field for m in addition_list.mapped_fields},
        )
        if addition_list
        else (Decimal("0"), 0)
    )
    rf_amount, rf_row = get_movement_transaction_amount(
        rollforward,
        transaction_key="purchase",
        measure="original_value",
    )
    test_purchase = _amount(addition_test, "purchase_population_amount")
    test_rf = _amount(addition_test, "rollforward_purchase_amount")
    test_diff = _amount(addition_test, "difference_amount")
    sad = field_values(lead).get("sad") if lead else None
    return _observation(
        checked_data=[
            _addition_list_item(
                addition_list,
                None,
                section="K.02.1 新增清单购置金额汇总",
                key_columns=["original_value", "addition_method"],
                values_read=[
                    _value_read("新增清单购置原值合计", addition_total, amount_type="新增清单金额"),
                ],
                missing_data=[] if addition_list else ["新增清单"],
            ),
            _amounts_item(
                addition_test,
                section="K.02.1 测试页购置金额与差异",
                keys=["purchase_population_amount", "rollforward_purchase_amount", "difference_amount"],
            ),
            _rollforward_item(rollforward, rf_amount, rf_row),
            _lead_item(lead, "SAD", sad),
        ],
        check_logic="读取新增清单购置金额、K.02.1 测试页购置金额/后推购置金额/差异、K.01 后推购置金额和 Lead SAD，用于核对新增测试总体与后推表购置金额是否一致。",
        expected_result="新增清单购置金额、K.02.1 测试页金额与 K.01 后推购置金额应一致；存在差异时应结合 SAD 和说明提示复核。",
        actual_result=(
            f"新增清单购置合计={_text(addition_total)}，测试页购置={_text(test_purchase.amount if test_purchase else None)}，"
            f"测试页后推购置={_text(test_rf.amount if test_rf else None)}，测试页差异={_text(test_diff.amount if test_diff else None)}，"
            f"K.01购置={_text(rf_amount)}，SAD={_text(sad)}。"
        ),
        result_summary=_result_summary(issues),
    )


def build_addition_sample_match_evidence_observation(
    addition_test: AdditionTestSheetDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
    execution_path: AdditionExecutionPathDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    preview = build_addition_consistency_preview(
        addition_test,
        addition_sample_output,
        execution_path=execution_path,
    )
    return _observation(
        checked_data=[
            _execution_path_item(execution_path),
            _sample_output_item(addition_sample_output, rows=_sample_output_rows(addition_sample_output)),
            _tested_samples_item(addition_test, rows=_tested_sample_rows(addition_test)),
        ],
        check_logic="读取 K.02.1a 已选样本和 K.02.1 实际测试样本，按资产编号、资产名称和原值匹配，检查已选样本是否进入测试页。",
        expected_result="K.02.1a 已选取样本应能在 K.02.1 测试页找到对应测试记录；关键项目金额应与实际测试样本一致。",
        actual_result=(
            f"已选样本 {preview.selected_count} 条，测试样本 {preview.tested_count} 条，"
            f"匹配 {preview.matched_count} 条，未匹配已选样本 {len(preview.unmatched_selected)} 条，"
            f"未匹配测试样本 {len(preview.unmatched_tested)} 条。"
        ),
        result_summary=_result_summary(issues),
    )


def build_addition_sample_pool_observation(
    addition_list: FaListDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
    rollforward: RollforwardSheetDataset | None,
    addition_test: AdditionTestSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    sample_pool = _amount(addition_sample_output, "sample_pool_amount")
    rf_amount, rf_row = get_movement_transaction_amount(
        rollforward,
        transaction_key="purchase",
        measure="original_value",
    )
    test_rf = _amount(addition_test, "rollforward_purchase_amount")
    return _observation(
        checked_data=[
            _amounts_item(addition_sample_output, section="K.02.1a 样本池金额", keys=["sample_pool_amount"]),
            _amounts_item(addition_test, section="K.02.1 测试页后推购置金额", keys=["rollforward_purchase_amount"]),
            _rollforward_item(rollforward, rf_amount, rf_row),
            _addition_list_item(
                addition_list,
                None,
                section="K.02.1 新增清单购置记录",
                key_columns=["original_value", "addition_method"],
                values_read=[
                    _value_read(
                        "新增清单购置原值合计",
                        _purchase_total(addition_list),
                        amount_type="新增清单金额",
                    )
                ],
                missing_data=[] if addition_list else ["新增清单"],
            ),
        ],
        check_logic="读取 K.02.1a 样本池总体金额，并与 K.02.1 测试页或 K.01 后推表的购置金额进行核对。",
        expected_result="样本池总体金额应与新增购置测试总体金额一致，确保抽样总体与被测试总体一致。",
        actual_result=(
            f"样本池金额={_text(sample_pool.amount if sample_pool else None)}，"
            f"测试页后推购置={_text(test_rf.amount if test_rf else None)}，K.01购置={_text(rf_amount)}。"
        ),
        result_summary=_result_summary(issues),
    )


def build_addition_te_cra_observation(
    addition_sample_output: AdditionSampleOutputDataset | None,
    lead: LeadSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    te = _parameter(addition_sample_output, "te")
    cra = _parameter(addition_sample_output, "cra")
    assertions = _parameter(addition_sample_output, "covered_assertions")
    lead_values = field_values(lead) if lead else {}
    return _observation(
        checked_data=[
            _parameters_item(addition_sample_output, keys=["te", "cra", "covered_assertions"]),
            _lead_item(lead, "TE", lead_values.get("te")),
            _lead_cra_item(lead),
        ],
        check_logic="读取 K.02.1a 抽样参数中的 TE、综合风险评估和覆盖认定，并与 Lead Sheet 的 TE 和相关 CRA 行核对。",
        expected_result="K.02.1a 使用的 TE 和 CRA 应与 Lead Sheet 中对应参数一致；覆盖认定应能对应到 Lead 的 CRA 评估。",
        actual_result=(
            f"K.02.1a TE={_text(te.value if te else None)}，CRA={_text(cra.value if cra else None)}，"
            f"覆盖认定={_text(assertions.value if assertions else None)}，Lead TE={_text(lead_values.get('te'))}，"
            f"Lead CRA 行数={len(lead.cra_rows) if lead else 0}。"
        ),
        result_summary=_result_summary(issues),
    )


def build_addition_assertions_observation(
    addition_sample_output: AdditionSampleOutputDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    assertions = _parameter(addition_sample_output, "covered_assertions")
    return _observation(
        checked_data=[
            _parameters_item(addition_sample_output, keys=["covered_assertions"]),
        ],
        check_logic="读取 K.02.1a 抽样输出中的测试覆盖认定，检查新增 TOD 是否包含完整性等通常不由从账面到证据的测试直接覆盖的认定。",
        expected_result="新增 TOD 通常覆盖存在/发生、计价/计量、权利义务等认定；如包含完整性，应提示人工确认是否有额外程序支持。",
        actual_result=f"本次读取到的覆盖认定为：{_text(assertions.value if assertions else None)}。",
        result_summary=_result_summary(issues),
    )


def build_addition_replacement_reason_observation(
    addition_test: AdditionTestSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    replacement_rows = [
        row.source_row
        for row in (addition_test.tested_samples if addition_test else [])
        if _contains_replacement(row.sample_type)
    ]
    return _observation(
        checked_data=[
            _tested_samples_item(addition_test, rows=replacement_rows),
        ],
        check_logic="读取 K.02.1 测试页中的测试样本类型和证据说明，检查替换样本是否记录原样本无法使用的原因。",
        expected_result="如启用替换样本，应说明原样本无法测试的原因和替换依据；未启用替换样本时不应触发 finding。",
        actual_result=f"本次读取测试样本 {len(addition_test.tested_samples) if addition_test else 0} 条，替换样本 {len(replacement_rows)} 条。",
        result_summary=_result_summary(issues),
    )


def build_addition_data_insufficient_observation(rule_id: str, reason: str) -> dict:
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
        check_logic="本规则依赖新增清单或 K.02.1 新增测试资料；资料不足时只记录未执行原因，不读取或推断底稿数值。",
        expected_result="应先识别到规则所需资料后，再执行新增测试相关检查。",
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


def _addition_list_item(
    addition_list: FaListDataset | None,
    ctx: ColumnContext | None,
    *,
    section: str,
    key_columns: list[str],
    values_read: list[dict],
    missing_data: list[str],
    rows: list[int | None] | None = None,
) -> dict:
    mapped_headers = ctx.mapped_headers if ctx else {m.standard_field: m.source_header for m in addition_list.mapped_fields} if addition_list else {}
    mapped_columns = ctx.mapped_columns if ctx else {m.standard_field: m.column_index for m in addition_list.mapped_fields} if addition_list else {}
    matched_rows = _clean_ints(rows or _sample_rows(addition_list))
    matched_columns = [mapped_columns[field] for field in key_columns if field in mapped_columns]
    return {
        "sheet": addition_list.source_sheet if addition_list else (ctx.source_sheet if ctx else None),
        "section": section,
        "location": _location(matched_rows),
        "identified_by": {
            "sheet_name": addition_list.source_sheet if addition_list else (ctx.source_sheet if ctx else None),
            "section": section,
            "matched_keywords": [mapped_headers.get(field, field) for field in key_columns if field in mapped_headers],
            "matched_rows": matched_rows,
            "matched_columns": matched_columns,
        },
        "key_columns": key_columns,
        "values_read": values_read,
        "missing_data": missing_data,
    }


def _execution_path_item(execution_path: AdditionExecutionPathDataset | None) -> dict:
    return {
        "sheet": None,
        "section": "K.02.1 执行路径识别",
        "location": _location([execution_path.summary_source_row] if execution_path else []),
        "identified_by": {
            "sheet_name": None,
            "section": "K.02.1 执行路径识别",
            "matched_keywords": [execution_path.path_kind] if execution_path else [],
            "matched_rows": [execution_path.summary_source_row] if execution_path and execution_path.summary_source_row else [],
            "matched_columns": [],
        },
        "key_columns": ["path_kind", "addition_list_sheet", "addition_test_sheet", "addition_sample_output_sheet"],
        "values_read": [
            _value_read("执行路径", execution_path.path_kind, amount_type="ingest"),
            _value_read("识别置信度", execution_path.recognition_confidence, amount_type="ingest"),
        ] if execution_path else [],
        "missing_data": [] if execution_path else ["K.02.1 执行路径识别结果"],
    }


def _sample_output_item(
    addition_sample_output: AdditionSampleOutputDataset | None,
    *,
    rows: list[int | None],
) -> dict:
    return {
        "sheet": addition_sample_output.source_sheet if addition_sample_output else None,
        "section": "K.02.1a 已选样本",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": addition_sample_output.source_sheet if addition_sample_output else None,
            "section": "selected_samples",
            "matched_keywords": ["已选样本", "样本类型", "资产编号", "原值"],
            "matched_rows": _clean_ints(rows),
            "matched_columns": [],
        },
        "key_columns": ["sample_type", "asset_id", "asset_name", "original_value"],
        "values_read": _sample_row_values(addition_sample_output),
        "missing_data": [] if addition_sample_output else ["K.02.1a 新增选样输出"],
    }


def _tested_samples_item(
    addition_test: AdditionTestSheetDataset | None,
    *,
    rows: list[int | None],
) -> dict:
    return {
        "sheet": addition_test.source_sheet if addition_test else None,
        "section": "K.02.1 实际测试样本",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": addition_test.source_sheet if addition_test else None,
            "section": "tested_samples",
            "matched_keywords": ["测试样本", "样本类型", "资产编号", "原值", "证据说明"],
            "matched_rows": _clean_ints(rows),
            "matched_columns": [],
        },
        "key_columns": ["sample_type", "asset_id", "asset_name", "original_value", "evidence_description"],
        "values_read": _tested_row_values(addition_test, rows),
        "missing_data": [] if addition_test else ["K.02.1 新增测试"],
    }


def _amounts_item(dataset: object | None, *, section: str, keys: list[str]) -> dict:
    amounts = getattr(dataset, "amounts", {}) if dataset else {}
    rows = [amounts[key].source_row for key in keys if key in amounts]
    columns = [amounts[key].source_column for key in keys if key in amounts and amounts[key].source_column]
    return {
        "sheet": getattr(dataset, "source_sheet", None),
        "section": section,
        "location": _location(rows),
        "identified_by": {
            "sheet_name": getattr(dataset, "source_sheet", None),
            "section": section,
            "matched_keywords": [amounts[key].label for key in keys if key in amounts],
            "matched_rows": _clean_ints(rows),
            "matched_columns": columns,
        },
        "key_columns": keys,
        "values_read": [
            _amount_value(amounts[key], amount_type=section)
            for key in keys
            if key in amounts
        ],
        "missing_data": [key for key in keys if key not in amounts],
    }


def _parameters_item(addition_sample_output: AdditionSampleOutputDataset | None, *, keys: list[str]) -> dict:
    parameters = addition_sample_output.parameters if addition_sample_output else {}
    rows = [parameters[key].source_row for key in keys if key in parameters]
    columns = [parameters[key].source_column for key in keys if key in parameters and parameters[key].source_column]
    return {
        "sheet": addition_sample_output.source_sheet if addition_sample_output else None,
        "section": "K.02.1a 抽样参数",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": addition_sample_output.source_sheet if addition_sample_output else None,
            "section": "parameters",
            "matched_keywords": [parameters[key].label for key in keys if key in parameters],
            "matched_rows": _clean_ints(rows),
            "matched_columns": columns,
        },
        "key_columns": keys,
        "values_read": [
            _parameter_value(parameters[key], amount_type="K.02.1a 抽样参数")
            for key in keys
            if key in parameters
        ],
        "missing_data": [key for key in keys if key not in parameters],
    }


def _rollforward_item(
    rollforward: RollforwardSheetDataset | None,
    amount: Decimal | None,
    row: int | None,
) -> dict:
    return {
        "sheet": rollforward.source_sheet if rollforward else None,
        "section": "K.01 后推购置金额",
        "location": _location([row]),
        "identified_by": {
            "sheet_name": rollforward.source_sheet if rollforward else None,
            "section": "movement_transactions",
            "matched_keywords": ["购置", "original_value"],
            "matched_rows": [row] if row else [],
            "matched_columns": [],
        },
        "key_columns": ["purchase", "original_value"],
        "values_read": [
            _value_read("K.01后推购置原值", amount, row=row, amount_type="K.01后推金额")
        ] if amount is not None else [],
        "missing_data": [] if amount is not None else ["K.01 后推购置金额"],
    }


def _lead_item(lead: LeadSheetDataset | None, label: str, value: object | None) -> dict:
    matched_rows = [
        field.source_row
        for field in (lead.basic_info_fields if lead else [])
        if field.label == label or field.field_key.lower() == label.lower()
    ]
    matched_columns = [
        field.source_col
        for field in (lead.basic_info_fields if lead else [])
        if (field.label == label or field.field_key.lower() == label.lower()) and field.source_col is not None
    ]
    return {
        "sheet": lead.source_sheet if lead else None,
        "section": f"K.00 Lead {label}",
        "location": _location(matched_rows),
        "identified_by": {
            "sheet_name": lead.source_sheet if lead else None,
            "section": "basic_info",
            "matched_keywords": [label],
            "matched_rows": matched_rows,
            "matched_columns": matched_columns,
        },
        "key_columns": [label.lower()],
        "values_read": [
            _value_read(label, value, row=matched_rows[0] if matched_rows else None, column=matched_columns[0] if matched_columns else None, amount_type="Lead参数")
        ] if value is not None else [],
        "missing_data": [] if value is not None else [f"Lead {label}"],
    }


def _lead_cra_item(lead: LeadSheetDataset | None) -> dict:
    rows = [row.source_row for row in (lead.cra_rows if lead else []) if row.source_row is not None]
    return {
        "sheet": lead.source_sheet if lead else None,
        "section": "K.00 Lead CRA",
        "location": _location(rows),
        "identified_by": {
            "sheet_name": lead.source_sheet if lead else None,
            "section": "cra_rows",
            "matched_keywords": [row.assertion for row in (lead.cra_rows if lead else []) if row.assertion],
            "matched_rows": rows,
            "matched_columns": [],
        },
        "key_columns": ["assertion", "cra"],
        "values_read": [
            _value_read(row.assertion or "CRA", row.cra, row=row.source_row, amount_type="Lead CRA")
            for row in (lead.cra_rows if lead else [])[:10]
        ],
        "missing_data": [] if lead and lead.cra_rows else ["Lead CRA"],
    }


def _record_values(
    addition_list: FaListDataset | None,
    rows: list[int | None],
    *,
    fields: list[str] | None = None,
) -> list[dict]:
    if addition_list is None:
        return []
    wanted_rows = set(_clean_ints(rows)) or {record.source_row for record in addition_list.records[:3]}
    fields = fields or ["asset_id", "asset_name", "asset_category", "start_date", "original_value", "addition_method"]
    values = []
    for record in addition_list.records:
        if record.source_row not in wanted_rows:
            continue
        for field in fields:
            values.append(
                _value_read(field, getattr(record, field, None), row=record.source_row, amount_type="新增清单字段")
            )
    return values[:30]


def _sample_row_values(addition_sample_output: AdditionSampleOutputDataset | None) -> list[dict]:
    values = []
    for row in (addition_sample_output.selected_samples if addition_sample_output else [])[:5]:
        values.extend(
            [
                _value_read("样本类型", row.sample_type, row=row.source_row, amount_type="K.02.1a样本"),
                _value_read("资产编号", row.asset_id, row=row.source_row, amount_type="K.02.1a样本"),
                _value_read("原值", row.original_value, row=row.source_row, amount_type="K.02.1a样本"),
            ]
        )
    return values[:30]


def _tested_row_values(addition_test: AdditionTestSheetDataset | None, rows: list[int | None]) -> list[dict]:
    wanted_rows = set(_clean_ints(rows)) or {row.source_row for row in (addition_test.tested_samples if addition_test else [])[:5]}
    values = []
    for row in (addition_test.tested_samples if addition_test else []):
        if row.source_row not in wanted_rows:
            continue
        values.extend(
            [
                _value_read("样本类型", row.sample_type, row=row.source_row, amount_type="K.02.1测试样本"),
                _value_read("资产编号", row.asset_id, row=row.source_row, amount_type="K.02.1测试样本"),
                _value_read("原值", row.original_value, row=row.source_row, amount_type="K.02.1测试样本"),
                _value_read("证据说明", row.evidence_description, row=row.source_row, amount_type="K.02.1测试样本"),
            ]
        )
    return values[:30]


def _amount_value(item: AdditionAmountItem, *, amount_type: str) -> dict:
    return _value_read(
        item.label,
        parse_amount(item.amount) if parse_amount(item.amount) is not None else item.amount,
        row=item.source_row,
        column=item.source_column,
        amount_type=amount_type,
    )


def _parameter_value(item: AdditionParameterItem, *, amount_type: str) -> dict:
    return _value_read(
        item.label,
        parse_amount(item.value) if parse_amount(item.value) is not None else item.value,
        row=item.source_row,
        column=item.source_column,
        amount_type=amount_type,
    )


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


def _amount(dataset: object | None, key: str) -> AdditionAmountItem | None:
    amounts = getattr(dataset, "amounts", {}) if dataset else {}
    return amounts.get(key)


def _parameter(dataset: AdditionSampleOutputDataset | None, key: str) -> AdditionParameterItem | None:
    return dataset.parameters.get(key) if dataset else None


def _issue_rows(issues: list[QcIssue]) -> list[int | None]:
    return sorted({issue.source_row for issue in issues if issue.source_row is not None})


def _sample_rows(addition_list: FaListDataset | None) -> list[int | None]:
    return [record.source_row for record in (addition_list.records if addition_list else [])[:3]]


def _sample_output_rows(addition_sample_output: AdditionSampleOutputDataset | None) -> list[int | None]:
    return [row.source_row for row in (addition_sample_output.selected_samples if addition_sample_output else [])[:5]]


def _tested_sample_rows(addition_test: AdditionTestSheetDataset | None) -> list[int | None]:
    return [row.source_row for row in (addition_test.tested_samples if addition_test else [])[:5]]


def _contains_replacement(value: str | None) -> bool:
    text = (value or "").lower()
    return "替换" in text or "replacement" in text


def _rule_section(rule_id: str) -> str:
    return {
        "addition_required_fields": "K.02.1 新增清单字段完整性",
        "addition_population_homogeneity": "K.02.1 新增清单总体同质性",
        "addition_rollforward_reconciliation": "K.02.1 新增金额与后推表勾稽",
    }.get(rule_id, "K.02.1 新增测试")


def _purchase_total(addition_list: FaListDataset | None) -> Decimal | None:
    if addition_list is None:
        return None
    total, _ = sum_purchase_original_value(
        addition_list.records,
        {m.standard_field for m in addition_list.mapped_fields},
    )
    return total


def _result_summary(issues: list[QcIssue]) -> str:
    return f"触发 finding {len(issues)} 条。" if issues else "未触发 finding。"


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
        return float(value)
    return value


def _text(value: object | None) -> str:
    if value is None or value == "":
        return "未记录"
    return str(value)
