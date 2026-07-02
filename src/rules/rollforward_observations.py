from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount


_AMOUNT_FIELDS = [
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "net_value",
]


def build_rollforward_exists_observation(
    rollforward: RollforwardSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    missing = []
    if rollforward is None or not rollforward.source_sheet:
        missing.append("K.01 后推工作表")
    elif not rollforward.section_presence.get("b1_bkd_main_table", True):
        missing.append("K.01 表1 / BKD 主表区")
    return _observation(
        checked_data=[_sheet_item(rollforward, missing_data=missing)],
        check_logic="检查是否识别到 K.01 后推工作表，并确认后推主表可解析。",
        expected_result="应识别到 K.01 后推工作表，且能定位表1/BKD主表、表头或金额列。",
        actual_result=(
            "未识别到 K.01 后推工作表。"
            if rollforward is None or not rollforward.source_sheet
            else f"识别到工作表 {rollforward.source_sheet}，资料区块 {sum(1 for ok in rollforward.section_presence.values() if ok)} 个。"
        ),
        result_summary=_result_summary(issues),
    )


def build_rollforward_columns_complete_observation(
    rollforward: RollforwardSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[_columns_item(rollforward)],
        check_logic="读取 K.01 后推表金额列绑定，检查原值、累计折旧、减值准备、净值在期初/变动/期末等口径下是否可识别。",
        expected_result="K.01 后推表应能识别关键金额列，支持后续勾稽和异常金额检查。",
        actual_result=f"本次识别到 {len(rollforward.amount_column_bindings) if rollforward else 0} 个金额列绑定。",
        result_summary=_result_summary(issues),
    )


def build_rollforward_abnormal_amounts_observation(
    rollforward: RollforwardSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[
            _totals_item(rollforward),
            _detail_records_item(rollforward, issues),
        ],
        check_logic="读取 K.01 后推表期初/期末合计及明细金额，检查累计折旧或减值是否超过原值、净值是否为负、合计原值是否异常为负。",
        expected_result="后推表金额关系应符合固定资产基本口径，净值不应异常为负，累计折旧和减值不应超过原值。",
        actual_result=f"本次读取 {len(rollforward.detail_records) if rollforward else 0} 行后推明细，异常金额 finding {len(issues)} 条。",
        result_summary=_result_summary(issues),
    )


def build_rollforward_difference_over_sad_observation(
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    sad = _sad_from_lead(lead)
    return _observation(
        checked_data=[
            _tb_reconciliation_item(rollforward),
            _sad_item(lead, sad),
        ],
        check_logic="读取 K.01 变动/TB 核对区的差异金额，并与 K.00 Lead 的 SAD 比较；超过 SAD 时检查是否存在差异说明或 Notes。",
        expected_result="TB check 差异不应超过 SAD；如超过 SAD，应有可追溯的 Notes 或说明。",
        actual_result=(
            f"本次读取 TB 差异 {len(rollforward.tb_difference_values) if rollforward else 0} 个，"
            f"SAD={_text(sad)}，finding {len(issues)} 条。"
        ),
        result_summary=_result_summary(issues),
    )


def build_rollforward_depreciation_pl_observation(
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    sad = _sad_from_lead(lead)
    return _observation(
        checked_data=[
            _table4_item(rollforward),
            _sad_item(lead, sad),
        ],
        check_logic="读取 K.01 表4折旧费用与利润表科目核对差异，并与 SAD 比较；超过 SAD 时检查是否存在 Notes。",
        expected_result="表4折旧费用核对差异不应超过 SAD；如超过 SAD，应有可追溯说明。",
        actual_result=(
            f"本次读取表4差异={_text(rollforward.table4_difference if rollforward else None)}，"
            f"SAD={_text(sad)}，finding {len(issues)} 条。"
        ),
        result_summary=_result_summary(issues),
    )


def build_rollforward_notes_semantic_observation(
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[
            _tb_reconciliation_item(rollforward),
            _table4_item(rollforward),
            _sad_item(lead, _sad_from_lead(lead)),
        ],
        check_logic="在 LLM 语义复核已启用且已返回结果时，记录其实际查看的 K.01 差异、Notes 和 SAD 上下文；该记录不覆盖确定性规则结论。",
        expected_result="LLM 只辅助复核 Notes 说明是否充分，不应改变确定性规则的 finding 结论。",
        actual_result=f"本次 LLM Notes 语义复核产生 finding {len(issues)} 条。",
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


def _sheet_item(
    rollforward: RollforwardSheetDataset | None,
    *,
    missing_data: list[str] | None = None,
) -> dict:
    rows = _section_rows(rollforward)
    return _item(
        sheet=_sheet(rollforward),
        section="K.01 后推工作表识别",
        location=_rows_location(rows),
        keywords=["K.01", "Agree SL to GL", "后推", "BKD"],
        rows=rows,
        key_columns=["source_sheet", "section_presence", "recognition_confidence"],
        values=[
            _value_read("识别置信度", getattr(rollforward, "recognition_confidence", None), amount_type="ingest"),
            _value_read(
                "识别资料区块数",
                sum(1 for ok in rollforward.section_presence.values() if ok) if rollforward else None,
                amount_type="ingest",
            ),
        ] if rollforward else [],
        missing_data=missing_data or [],
    )


def _columns_item(rollforward: RollforwardSheetDataset | None) -> dict:
    bindings = rollforward.amount_column_bindings if rollforward else []
    return _item(
        sheet=_sheet(rollforward),
        section="K.01 后推金额列绑定",
        location=_rows_location([rollforward.header_row if rollforward else None]),
        keywords=[b.source_header for b in bindings],
        rows=[rollforward.header_row if rollforward else None],
        columns=[b.column_index for b in bindings],
        key_columns=["measure", "period_role", "source_header"],
        values=[
            _value_read(
                f"{b.measure}/{getattr(b.period_role, 'value', b.period_role)}",
                b.source_header,
                row=rollforward.header_row if rollforward else None,
                column=b.column_index,
                amount_type="金额列绑定",
            )
            for b in bindings[:20]
        ],
        missing_data=[] if bindings else ["金额列绑定"],
    )


def _totals_item(rollforward: RollforwardSheetDataset | None) -> dict:
    values = []
    if rollforward:
        for field in _AMOUNT_FIELDS:
            values.append(_value_read(f"期初 {field}", rollforward.opening_totals.get(field), row=rollforward.total_row, amount_type="K.01合计"))
            values.append(_value_read(f"期末 {field}", rollforward.ending_totals.get(field), row=rollforward.total_row, amount_type="K.01合计"))
    return _item(
        sheet=_sheet(rollforward),
        section="K.01 后推期初/期末合计",
        location=_rows_location([rollforward.total_row if rollforward else None]),
        keywords=["合计", "期初", "期末", "原值", "累计折旧", "净值"],
        rows=[rollforward.total_row if rollforward else None],
        key_columns=_AMOUNT_FIELDS,
        values=values[:20],
        missing_data=[] if values else ["期初/期末合计金额"],
    )


def _detail_records_item(
    rollforward: RollforwardSheetDataset | None,
    issues: list[QcIssue],
) -> dict:
    issue_rows = sorted({issue.source_row for issue in issues if issue.source_row is not None})
    if not issue_rows and rollforward:
        issue_rows = [record.source_row for record in rollforward.detail_records[:3] if record.source_row is not None]
    records = rollforward.detail_records if rollforward else []
    selected = [record for record in records if record.source_row in set(issue_rows)]
    values = []
    for record in selected[:4]:
        for field in _AMOUNT_FIELDS:
            values.append(_value_read(field, getattr(record, field, None), row=record.source_row, amount_type="K.01明细金额"))
    return _item(
        sheet=_sheet(rollforward),
        section="K.01 后推明细金额",
        location=_rows_location(issue_rows),
        keywords=["明细", "原值", "累计折旧", "净值"],
        rows=issue_rows,
        key_columns=_AMOUNT_FIELDS,
        values=values[:20],
        missing_data=[] if records else ["后推明细行"],
    )


def _tb_reconciliation_item(rollforward: RollforwardSheetDataset | None) -> dict:
    values = []
    if rollforward:
        values.extend(
            _value_read(f"TB差异 {idx}", value, row=rollforward.tb_difference_row, amount_type="TB差异")
            for idx, value in enumerate(rollforward.tb_difference_values, start=1)
        )
        if rollforward.tb_notes_text_present:
            values.append(_value_read("TB Notes", rollforward.tb_notes_text, row=rollforward.tb_notes_row, amount_type="差异说明"))
    return _item(
        sheet=_sheet(rollforward),
        section="K.01 变动/TB 核对区",
        location=_rows_location([rollforward.tb_difference_row if rollforward else None, rollforward.tb_notes_row if rollforward else None]),
        keywords=["TB", "Check", "差异", "Notes"],
        rows=[rollforward.tb_difference_row if rollforward else None, rollforward.tb_notes_row if rollforward else None],
        key_columns=["tb_difference_values", "tb_notes_text"],
        values=values[:20],
        missing_data=[] if values else ["TB check 差异或 Notes"],
    )


def _table4_item(rollforward: RollforwardSheetDataset | None) -> dict:
    values = []
    if rollforward:
        for idx, amount in enumerate(rollforward.table4_pl_amounts, start=1):
            values.append(_value_read(f"利润表折旧金额 {idx}", amount, row=rollforward.table4_pl_total_row, amount_type="表4折旧金额"))
        values.extend(
            [
                _value_read("利润表折旧合计", rollforward.table4_pl_total, row=rollforward.table4_pl_total_row, amount_type="表4折旧金额"),
                _value_read("后推折旧金额", rollforward.table4_rollforward_depreciation, row=rollforward.table4_rollforward_depreciation_row, amount_type="表4折旧金额"),
                _value_read("表4差异", rollforward.table4_difference, row=rollforward.table4_difference_row, amount_type="表4差异"),
            ]
        )
        if rollforward.table4_notes_text_present:
            values.append(_value_read("表4 Notes", rollforward.table4_notes_text, row=rollforward.table4_notes_row, amount_type="差异说明"))
    return _item(
        sheet=_sheet(rollforward),
        section="K.01 表4折旧费用与利润表核对",
        location=_rows_location([
            rollforward.table4_pl_total_row if rollforward else None,
            rollforward.table4_rollforward_depreciation_row if rollforward else None,
            rollforward.table4_difference_row if rollforward else None,
            rollforward.table4_notes_row if rollforward else None,
        ]),
        keywords=["表4", "折旧费用", "利润表", "差异", "Notes"],
        rows=[
            rollforward.table4_pl_total_row if rollforward else None,
            rollforward.table4_rollforward_depreciation_row if rollforward else None,
            rollforward.table4_difference_row if rollforward else None,
            rollforward.table4_notes_row if rollforward else None,
        ],
        key_columns=["table4_difference", "table4_notes_text"],
        values=values[:20],
        missing_data=[] if any(value["value"] for value in values) else ["表4折旧核对金额或 Notes"],
    )


def _sad_item(lead: LeadSheetDataset | None, sad: Decimal | None) -> dict:
    sad_row = None
    sad_col = None
    if lead:
        for field in lead.basic_info_fields:
            if field.field_key == "sad":
                sad_row = field.source_row
                sad_col = field.source_col
                break
    return _item(
        sheet=lead.source_sheet if lead else None,
        section="K.00 Lead SAD",
        location=_rows_location([sad_row]),
        keywords=["SAD", "名义金额"],
        rows=[sad_row],
        columns=[sad_col],
        key_columns=["sad"],
        values=[_value_read("SAD", sad, row=sad_row, column=sad_col, amount_type="审计阈值")] if sad is not None else [],
        missing_data=[] if sad is not None else ["SAD"],
    )


def _item(
    *,
    sheet: str | None,
    section: str,
    location: str | None,
    keywords: list[str | None],
    rows: list[int | None],
    key_columns: list[str],
    values: list[dict],
    missing_data: list[str],
    columns: list[int | None] | None = None,
) -> dict:
    return {
        "sheet": sheet,
        "section": section,
        "location": location,
        "identified_by": {
            "sheet_name": sheet,
            "section": section,
            "matched_keywords": [str(value) for value in keywords if value][:12],
            "matched_rows": _clean_ints(rows),
            "matched_columns": _clean_ints(columns or []),
        },
        "key_columns": key_columns[:12],
        "values_read": values[:20],
        "missing_data": missing_data[:12],
    }


def _value_read(
    label: str,
    value: object,
    *,
    row: int | None = None,
    column: int | None = None,
    amount_type: str | None = None,
) -> dict:
    return {
        "label": label,
        "value": None if value is None else str(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": None,
        "amount_type": amount_type,
    }


def _sad_from_lead(lead: LeadSheetDataset | None) -> Decimal | None:
    if lead is None:
        return None
    sad = parse_amount(field_values(lead).get("sad"))
    if sad is None or sad <= 0:
        return None
    return sad


def _section_rows(rollforward: RollforwardSheetDataset | None) -> list[int | None]:
    if rollforward is None:
        return []
    rows = []
    for region in rollforward.section_regions.values():
        rows.extend([region.anchor_row, region.start_row, region.end_row])
    return rows


def _sheet(rollforward: RollforwardSheetDataset | None) -> str | None:
    return rollforward.source_sheet if rollforward and rollforward.source_sheet else None


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


def _text(value: object) -> str:
    return "" if value is None else str(value)
