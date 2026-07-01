from __future__ import annotations

from collections.abc import Iterable

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import field_values
from rules.lead_required_fields import LEAD_REQUIRED_FIELD_KEYS
from rules.models import QcIssue, Severity

_FIELD_LABELS = {
    "client_name": "客户名称",
    "period_end": "期末",
    "analysis_date": "分析日期",
    "te": "TE",
    "sad": "SAD",
    "gaap": "适用会计准则",
    "currency": "记账本位币",
}


def build_lead_required_fields_observation(
    lead: LeadSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    if lead is None or not lead.source_sheet:
        return _observation(
            checked_data=[
                _checked_data(
                    sheet=None,
                    section="K.00 Lead Sheet 基础信息",
                    location=None,
                    matched_keywords=[],
                    matched_rows=[],
                    matched_columns=[],
                    key_columns=list(LEAD_REQUIRED_FIELD_KEYS),
                    values_read=[],
                    missing_data=["K.00 Lead Sheet"],
                )
            ],
            check_logic="检查是否识别到 K.00 Lead Sheet，并读取基础信息区的客户名称、期末、分析日期、TE、SAD、适用会计准则和记账本位币。",
            expected_result="Lead 基础信息区应完整填写上述必需字段。",
            actual_result="本次未识别到可用于检查的 K.00 Lead Sheet。",
            result_summary=_result_summary(issues),
        )

    fields_by_key = {field.field_key: field for field in lead.basic_info_fields}
    values = field_values(lead)
    missing = [
        _FIELD_LABELS.get(key, key)
        for key in LEAD_REQUIRED_FIELD_KEYS
        if not str(values.get(key) or "").strip()
    ]
    matched_rows = [
        field.source_row
        for key in LEAD_REQUIRED_FIELD_KEYS
        for field in [fields_by_key.get(key)]
        if field is not None and field.source_row is not None
    ]
    matched_columns = [
        field.source_col
        for key in LEAD_REQUIRED_FIELD_KEYS
        for field in [fields_by_key.get(key)]
        if field is not None and field.source_col is not None
    ]
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 基础信息",
                location=_rows_location(matched_rows),
                matched_keywords=[
                    fields_by_key[key].label
                    for key in LEAD_REQUIRED_FIELD_KEYS
                    if key in fields_by_key
                ],
                matched_rows=matched_rows,
                matched_columns=matched_columns,
                key_columns=list(LEAD_REQUIRED_FIELD_KEYS),
                values_read=[
                    _value_read(
                        label=_FIELD_LABELS.get(key, key),
                        value=values.get(key),
                        row=fields_by_key.get(key).source_row if key in fields_by_key else None,
                        column=fields_by_key.get(key).source_col if key in fields_by_key else None,
                        amount_type="Lead 基础信息",
                    )
                    for key in LEAD_REQUIRED_FIELD_KEYS
                ],
                missing_data=missing,
            )
        ],
        check_logic="逐项读取 Lead 基础信息区，检查客户名称、期末、分析日期、TE、SAD、适用会计准则和记账本位币是否为空。",
        expected_result="上述必需字段均应已填写，且能够追溯到 Lead Sheet 的具体行列。",
        actual_result=(
            f"本次识别到 {len(lead.basic_info_fields)} 个基础信息字段，"
            f"必需字段缺失 {len(missing)} 项。"
        ),
        result_summary=_result_summary(issues),
    )


def build_lead_ingest_readability_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    block_rows = [
        row
        for block in lead.blocks
        for row in (block.start_row, block.end_row)
        if row is not None
    ]
    missing = []
    if not lead.movement_rows:
        missing.append("Lead movement table rows")
    if not lead.usable_for_rules:
        missing.append("usable movement table structure")
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 资料识别质量",
                location=_rows_location(block_rows),
                matched_keywords=[block.anchor_text for block in lead.blocks if block.anchor_text],
                matched_rows=block_rows,
                matched_columns=[],
                key_columns=[
                    "blocks",
                    "movement_bindings",
                    "movement_rows",
                    "check_with_a3",
                ],
                values_read=[
                    _value_read(
                        label="识别到的资料区块数",
                        value=len(lead.blocks),
                        row=None,
                        column=None,
                        amount_type="ingest",
                    ),
                    _value_read(
                        label="识别到的 movement 行数",
                        value=len(lead.movement_rows),
                        row=None,
                        column=None,
                        amount_type="ingest",
                    ),
                    _value_read(
                        label="识别到的 movement 列绑定数",
                        value=len(lead.movement_bindings),
                        row=None,
                        column=None,
                        amount_type="ingest",
                    ),
                    _value_read(
                        label="是否可继续执行 Lead 明细规则",
                        value="是" if lead.usable_for_rules else "否",
                        row=None,
                        column=None,
                        amount_type="ingest_status",
                    ),
                ],
                missing_data=missing,
            )
        ],
        check_logic="检查 Lead 资料识别结果是否足以支撑后续 Lead 明细规则继续执行，重点看 movement table 行、列绑定和 Check with A3 / Diff 区域是否可靠。",
        expected_result="Lead movement table 应能稳定识别核心账户行和关键金额列，才能继续执行依赖 Lead 明细的规则。",
        actual_result=(
            f"本次识别到 {len(lead.blocks)} 个资料区块、"
            f"{len(lead.movement_rows)} 行 movement 数据、"
            f"{len(lead.movement_bindings)} 个 movement 列绑定；"
            f"可继续执行状态：{'是' if lead.usable_for_rules else '否'}。"
        ),
        result_summary=_result_summary(issues),
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


def _checked_data(
    *,
    sheet: str | None,
    section: str,
    location: str | None,
    matched_keywords: list[str],
    matched_rows: list[int | None],
    matched_columns: list[int | None],
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
            "matched_keywords": [str(value) for value in matched_keywords if value][:12],
            "matched_rows": _clean_ints(matched_rows),
            "matched_columns": _clean_ints(matched_columns),
        },
        "key_columns": key_columns[:12],
        "values_read": values_read[:20],
        "missing_data": missing_data[:12],
    }


def _value_read(
    *,
    label: str,
    value: object,
    row: int | None,
    column: int | None,
    amount_type: str,
) -> dict:
    return {
        "label": label,
        "value": "" if value is None else str(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": None,
        "amount_type": amount_type,
    }


def _result_summary(issues: list[QcIssue]) -> str:
    finding_count = sum(1 for issue in issues if issue.severity != Severity.PASS)
    if finding_count:
        return f"触发 finding {finding_count} 条。"
    return "未触发 finding。"


def _rows_location(rows: list[int | None]) -> str | None:
    clean = _clean_ints(rows)
    if not clean:
        return None
    return "行 " + ", ".join(str(row) for row in clean[:12])


def _clean_ints(values: list[int | None]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result[:12]


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
