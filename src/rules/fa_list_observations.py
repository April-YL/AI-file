from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity

_FIELD_LABELS = {
    "asset_id": "资产编号",
    "asset_name": "资产名称",
    "asset_category": "资产类别",
    "start_date": "入账日期",
    "useful_life_months": "使用寿命",
    "salvage_rate": "残值率",
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧",
    "impairment_provision": "减值准备",
    "net_value": "净值",
}


def build_required_fields_observation(
    records: list[AssetRecord],
    ctx: ColumnContext,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    missing = sorted({issue.field or "" for issue in issues if issue.source_row is None})
    blank_rows = sorted({issue.source_row for issue in issues if issue.source_row is not None})
    row_fields: dict[int, set[str]] = defaultdict(set)
    for issue in issues:
        if issue.source_row is None or not issue.field:
            continue
        for field in issue.field.split("|"):
            row_fields[issue.source_row].add(field)
    return _observation(
        checked_data=[
            _checked_data(
                ctx,
                section="FA list 字段映射与必填字段",
                key_columns=sorted(ctx.mapped_fields),
                values_read=_mapped_field_values(ctx),
                missing_data=[item for item in missing if item],
            ),
            _checked_data(
                ctx,
                section="FA list 资产明细行",
                key_columns=_unique(["asset_id", "asset_name"] + sorted(ctx.mapped_fields)),
                values_read=_row_field_values(ctx, records, row_fields=row_fields),
                matched_rows=blank_rows,
                missing_data=[],
            ),
        ],
        check_logic="检查 FA list 是否识别到必需字段，并逐行检查已识别字段是否存在关键值为空。",
        expected_result="FA list 应至少包含资产编号或资产名称，并且已识别的核心字段不应为空。",
        actual_result=(
            f"本次识别到 {len(ctx.mapped_fields)} 个字段，读取 {len(records)} 行资产明细，"
            f"字段缺失 {len(missing)} 项，行级空值异常 {len(blank_rows)} 行。"
        ),
        result_summary=_result_summary(issues),
    )


def build_unique_asset_id_observation(
    records: list[AssetRecord],
    ctx: ColumnContext,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    duplicated_rows = sorted({issue.source_row for issue in issues if issue.source_row is not None})
    duplicated_ids = sorted({issue.asset_id for issue in issues if issue.asset_id})
    return _observation(
        checked_data=[
            _checked_data(
                ctx,
                section="FA list 资产编号唯一性",
                key_columns=["asset_id", "asset_name"],
                values_read=_row_identity_values(ctx, records, rows=duplicated_rows),
                matched_rows=duplicated_rows,
                missing_data=[] if "asset_id" in ctx.mapped_fields else ["asset_id"],
            )
        ],
        check_logic="按资产编号汇总 FA list 明细行，检查同一资产编号是否重复出现。",
        expected_result="同一资产编号在 FA list 中应只出现一次。",
        actual_result=(
            f"本次读取 {len(records)} 行资产明细，"
            f"发现 {len(duplicated_ids)} 个重复资产编号，涉及 {len(duplicated_rows)} 行。"
        ),
        result_summary=_result_summary(issues),
    )


def build_asset_value_consistency_observation(
    records: list[AssetRecord],
    ctx: ColumnContext,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    issue_rows = sorted({issue.source_row for issue in issues if issue.source_row is not None})
    rows = issue_rows or [record.source_row for record in records[:3] if record.source_row is not None]
    amount_fields = [
        "original_value",
        "accumulated_depreciation",
        "impairment_provision",
        "net_value",
    ]
    missing = [field for field in amount_fields[:3] if field not in ctx.mapped_fields]
    if "net_value" not in ctx.mapped_fields:
        missing.append("net_value")
    return _observation(
        checked_data=[
            _checked_data(
                ctx,
                section="FA list 金额勾稽字段",
                key_columns=amount_fields,
                values_read=_amount_values(ctx, records, rows=rows),
                matched_rows=rows,
                missing_data=missing,
            )
        ],
        check_logic="逐行检查净值是否等于原值减累计折旧及减值准备；累计折旧和减值准备按抵减金额处理。",
        expected_result="每行净值应与按原值、累计折旧和减值准备重新计算的金额一致，差异应在允许容差内。",
        actual_result=(
            f"本次读取 {len(records)} 行资产明细，"
            f"金额字段缺失 {len(missing)} 项，净值勾稽异常 {len(issue_rows)} 行。"
        ),
        result_summary=_result_summary(issues),
    )


def build_asset_amount_non_negative_observation(
    records: list[AssetRecord],
    ctx: ColumnContext,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    fields = ["original_value", "impairment_provision", "net_value"]
    issue_rows = _issue_rows(issues)
    rows = issue_rows or _sample_rows(records)
    missing = [field for field in fields if field not in ctx.mapped_fields]
    return _observation(
        checked_data=[
            _checked_data(
                ctx,
                section="FA list 金额非负检查",
                key_columns=fields,
                values_read=_field_values(ctx, records, rows=rows, fields=fields, amount_type="金额"),
                matched_rows=rows,
                missing_data=missing,
            )
        ],
        check_logic="逐行读取 FA list 的原值、减值准备和净值，检查这些金额是否存在负数。",
        expected_result="原值、减值准备和净值不应为负数；如出现负数，应由审计人员核对金额符号或调整事项。",
        actual_result=f"本次读取 {len(records)} 行资产明细，金额非负异常 {len(issue_rows)} 行。",
        result_summary=_result_summary(issues),
    )


def build_useful_life_positive_observation(
    records: list[AssetRecord],
    ctx: ColumnContext,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    fields = ["useful_life_months"]
    issue_rows = _issue_rows(issues)
    rows = issue_rows or _sample_rows(records)
    missing = [field for field in fields if field not in ctx.mapped_fields]
    return _observation(
        checked_data=[
            _checked_data(
                ctx,
                section="FA list 使用寿命检查",
                key_columns=fields,
                values_read=_field_values(ctx, records, rows=rows, fields=fields, amount_type="使用寿命"),
                matched_rows=rows,
                missing_data=missing,
            )
        ],
        check_logic="逐行读取 FA list 的使用寿命字段，检查其是否能解析为正数月份或正数年限。",
        expected_result="使用寿命应为可解析的正数；无法解析或小于等于零时，需要复核或修正。",
        actual_result=f"本次读取 {len(records)} 行资产明细，使用寿命异常 {len(issue_rows)} 行。",
        result_summary=_result_summary(issues),
    )


def build_salvage_rate_range_observation(
    records: list[AssetRecord],
    ctx: ColumnContext,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    fields = ["salvage_rate"]
    issue_rows = _issue_rows(issues)
    rows = issue_rows or _sample_rows(records)
    missing = [field for field in fields if field not in ctx.mapped_fields]
    return _observation(
        checked_data=[
            _checked_data(
                ctx,
                section="FA list 残值率范围检查",
                key_columns=fields,
                values_read=_field_values(ctx, records, rows=rows, fields=fields, amount_type="残值率"),
                matched_rows=rows,
                missing_data=missing,
            )
        ],
        check_logic="逐行读取 FA list 的残值率字段，检查其是否能解析为比例，并判断是否落在 0 到 1 的范围内；百分比格式仅提示确认口径。",
        expected_result="残值率应为 0 到 1 之间的比例，或可明确换算为该范围内的百分比。",
        actual_result=f"本次读取 {len(records)} 行资产明细，残值率异常或需确认 {len(issue_rows)} 行。",
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
    ctx: ColumnContext,
    *,
    section: str,
    key_columns: list[str],
    values_read: list[dict],
    missing_data: list[str],
    matched_rows: list[int | None] | None = None,
) -> dict:
    key_columns = key_columns[:12]
    clean_rows = [row for row in (matched_rows or []) if row is not None][:12]
    matched_columns = [
        ctx.mapped_columns[field]
        for field in key_columns
        if field in ctx.mapped_columns
    ][:12]
    matched_keywords = [
        ctx.mapped_headers.get(field) or _field_label(field)
        for field in key_columns
        if field in ctx.mapped_fields
    ][:12]
    return {
        "sheet": ctx.source_sheet,
        "section": section,
        "location": _location(clean_rows),
        "identified_by": {
            "sheet_name": ctx.source_sheet,
            "section": section,
            "matched_keywords": matched_keywords,
            "matched_rows": clean_rows,
            "matched_columns": matched_columns,
        },
        "key_columns": key_columns,
        "values_read": values_read[:20],
        "missing_data": missing_data[:12],
    }


def _mapped_field_values(ctx: ColumnContext) -> list[dict]:
    values: list[dict] = []
    for field in sorted(ctx.mapped_fields):
        column = ctx.mapped_columns.get(field)
        values.append(
            _value_read(
                label=_field_label(field),
                value=ctx.mapped_headers.get(field) or field,
                row=None,
                column=column,
                amount_type="字段映射",
            )
        )
    return values


def _row_identity_values(
    ctx: ColumnContext,
    records: list[AssetRecord],
    *,
    rows: list[int | None],
) -> list[dict]:
    wanted = {row for row in rows if row is not None}
    selected = [record for record in records if record.source_row in wanted]
    if not selected:
        selected = records[:3]
    values: list[dict] = []
    for record in selected:
        for field in ("asset_id", "asset_name"):
            if field not in ctx.mapped_fields:
                continue
            values.append(
                _record_value(
                    ctx,
                    record,
                    field,
                    amount_type="资产标识",
                )
            )
    return values


def _row_field_values(
    ctx: ColumnContext,
    records: list[AssetRecord],
    *,
    row_fields: dict[int, set[str]],
) -> list[dict]:
    values: list[dict] = []
    by_row = {record.source_row: record for record in records}
    for row in sorted(row_fields):
        record = by_row.get(row)
        if record is None:
            continue
        fields = _unique(["asset_id", "asset_name"] + sorted(row_fields[row]))
        for field in fields:
            if field not in ctx.mapped_fields:
                continue
            values.append(
                _record_value(
                    ctx,
                    record,
                    field,
                    amount_type="字段值",
                )
            )
    return values


def _amount_values(
    ctx: ColumnContext,
    records: list[AssetRecord],
    *,
    rows: list[int | None],
) -> list[dict]:
    wanted = {row for row in rows if row is not None}
    selected = [record for record in records if record.source_row in wanted]
    values: list[dict] = []
    for record in selected:
        for field in (
            "original_value",
            "accumulated_depreciation",
            "impairment_provision",
            "net_value",
        ):
            if field not in ctx.mapped_fields:
                continue
            values.append(
                _record_value(
                    ctx,
                    record,
                    field,
                    amount_type="金额",
                )
            )
    return values


def _field_values(
    ctx: ColumnContext,
    records: list[AssetRecord],
    *,
    rows: list[int | None],
    fields: list[str],
    amount_type: str,
) -> list[dict]:
    wanted = {row for row in rows if row is not None}
    selected = [record for record in records if record.source_row in wanted]
    values: list[dict] = []
    for record in selected:
        for field in fields:
            if field not in ctx.mapped_fields:
                continue
            values.append(
                _record_value(
                    ctx,
                    record,
                    field,
                    amount_type=amount_type,
                )
            )
    return values


def _record_value(
    ctx: ColumnContext,
    record: AssetRecord,
    field: str,
    *,
    amount_type: str,
) -> dict:
    column = ctx.mapped_columns.get(field)
    return _value_read(
        label=_field_label(field),
        value=getattr(record, field, None),
        row=record.source_row,
        column=column,
        amount_type=amount_type,
    )


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


def _field_label(field: str) -> str:
    return _FIELD_LABELS.get(field, field)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _issue_rows(issues: list[QcIssue]) -> list[int]:
    return sorted({issue.source_row for issue in issues if issue.source_row is not None})


def _sample_rows(records: list[AssetRecord]) -> list[int]:
    return [record.source_row for record in records[:3] if record.source_row is not None]


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
