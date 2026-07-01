from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from ingest.models import RollforwardPeriodRole
from rules.lead_common import (
    amounts_close,
    lead_book_balance,
    movement_field_key,
    parse_threshold_amount,
)
from rules.models import QcIssue, Severity

RULE_ID = "lead_rollforward_tb_reconciliation"

_FIELD_LABELS = {
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧",
    "impairment_provision": "减值准备",
    "net_value": "净值",
}

_HOW_FIELD_LABELS = dict(_FIELD_LABELS)


def _check_from_k01_check_column(
    rollforward: RollforwardSheetDataset,
) -> list[QcIssue] | None:
    """优先读取 K.01 表1 CHECK 列；不可读时返回 None 走旧兜底逻辑。"""
    checks = getattr(rollforward, "table1_check_values", None) or {}
    if not checks:
        return None

    differences: dict[str, tuple[object, int | None]] = {}
    rows = getattr(rollforward, "table1_check_rows", None) or {}
    for field_key in (
        "original_value",
        "accumulated_depreciation",
        "impairment_provision",
        "net_value",
    ):
        diff = checks.get(field_key)
        if diff is None or amounts_close(diff, 0, ref=max(abs(diff), 1)):
            continue
        differences[field_key] = (diff, rows.get(field_key))
    return _group_period_differences(
        differences,
        period_label="期末",
        source_sheet=rollforward.source_sheet,
        procedure_code="K.01",
    )





def build_lead_rollforward_tb_reconciliation_observation(
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> dict:
    if lead is None or not lead.source_sheet:
        return _evidence_observation(
            checked_data=[
                _evidence_item(
                    sheet=None,
                    section="K.00 Lead 固定资产余额行",
                    missing_data=["未识别到 K.00 Lead Sheet"],
                )
            ],
            check_logic="未取得 Lead 固定资产余额行，未执行 Lead 与 K.01 勾稽检查。",
            expected_result="应识别到 Lead 中固定资产原值、累计折旧、减值准备、净值余额行。",
            actual_result="未识别到 Lead 资料。",
            result_summary="资料不足，未触发 finding。",
        )
    if rollforward is None or not (rollforward.ending_totals or rollforward.opening_totals):
        return _evidence_observation(
            checked_data=[
                _lead_evidence_item(lead),
                _evidence_item(
                    sheet=_rf_sheet(rollforward),
                    section="K.01 后推汇总",
                    missing_data=["未识别到 K.01 后推期初/期末汇总金额"],
                ),
            ],
            check_logic="已读取 Lead 固定资产余额行，但未取得 K.01 后推汇总金额，无法执行勾稽。",
            expected_result="K.01 应包含可用于勾稽的后推汇总金额或 Check 列。",
            actual_result="K.01 后推汇总金额未识别。",
            result_summary="资料不足，未触发 finding。",
        )

    checks = getattr(rollforward, "table1_check_values", None) or {}
    if checks:
        rows = getattr(rollforward, "table1_check_rows", None) or {}
        non_zero = [
            value
            for value in checks.values()
            if value is not None and not amounts_close(value, 0, ref=max(abs(value), 1))
        ]
        return _evidence_observation(
            checked_data=[
                _evidence_item(
                    sheet=rollforward.source_sheet,
                    section="K.01 表1后推汇总 Check 列",
                    location=_rows_location(rows.values()),
                    identified_by=_identified_by(
                        sheet=rollforward.source_sheet,
                        section="table1_check_values",
                        keywords=["K.01", "表1", "Check", "原值", "累计折旧", "净值"],
                        rows=rows.values(),
                    ),
                    key_columns=["原值", "累计折旧", "减值准备", "净值", "Check"],
                    values_read=[
                        _value_read(
                            _HOW_FIELD_LABELS.get(field_key, field_key) + " Check",
                            value,
                            row=rows.get(field_key),
                            amount_type="勾稽差异",
                        )
                        for field_key, value in checks.items()
                        if field_key in _HOW_FIELD_LABELS
                    ],
                )
            ],
            check_logic="优先使用 K.01 表1 Check 列判断后推汇总与账面/TB是否一致。",
            expected_result="原值、累计折旧、减值准备、净值的 Check 均应为 0。",
            actual_result=f"识别到 {len(checks)} 个 Check 值，其中非零差异 {len(non_zero)} 个。",
            result_summary=f"触发 finding {1 if non_zero else 0} 条。",
        )

    ending_diffs, compared_fields = _direct_differences(lead, rollforward, period="ending")
    opening_diffs, _opening_compared = _direct_differences(lead, rollforward, period="opening")
    finding_count = (1 if ending_diffs else 0) + (1 if opening_diffs else 0)
    return _evidence_observation(
        checked_data=[
            _lead_evidence_item(lead),
            _rollforward_totals_evidence_item(rollforward),
        ],
        check_logic="K.01 表1 Check 列未识别时，改用 Lead 固定资产余额与 K.01 后推汇总金额直接比对。",
        expected_result="Lead 与 K.01 对应项目的期初、期末金额应一致，差异应为 0。",
        actual_result=f"直接比对 {compared_fields} 个期末项目，发现差异项目 {len(ending_diffs) + len(opening_diffs)} 个。",
        result_summary=f"触发 finding {finding_count} 条。",
    )


def _evidence_observation(
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


def _evidence_item(
    *,
    sheet: str | None,
    section: str,
    location: str | None = None,
    identified_by: dict | None = None,
    key_columns: list[str] | None = None,
    values_read: list[dict] | None = None,
    missing_data: list[str] | None = None,
) -> dict:
    return {
        "sheet": sheet,
        "section": section,
        "location": location,
        "identified_by": identified_by
        or _identified_by(sheet=sheet, section=section, keywords=[], rows=[]),
        "key_columns": key_columns or [],
        "values_read": values_read or [],
        "missing_data": missing_data or [],
    }


def _identified_by(
    *,
    sheet: str | None,
    section: str,
    keywords: list[str],
    rows,
) -> dict:
    return {
        "sheet_name": sheet,
        "section": section,
        "matched_keywords": keywords,
        "matched_rows": [row for row in rows if isinstance(row, int)],
        "matched_columns": [],
    }


def _value_read(
    label: str,
    value: object,
    *,
    row: int | None = None,
    amount_type: str | None = None,
) -> dict:
    return {
        "label": label,
        "value": None if value is None else str(value),
        "row": row,
        "column": None,
        "cell": None,
        "unit": None,
        "amount_type": amount_type,
    }


def _rows_location(rows) -> str | None:
    row_list = sorted({row for row in rows if isinstance(row, int)})
    if not row_list:
        return None
    return "行 " + ", ".join(str(row) for row in row_list)


def _lead_evidence_item(lead: LeadSheetDataset) -> dict:
    rows = []
    values = []
    for row in lead.movement_rows:
        field_key = movement_field_key(row.account_label)
        if field_key is None:
            continue
        rows.append(row.source_row)
        values.append(
            _value_read(
                _HOW_FIELD_LABELS.get(field_key, field_key) + " Lead期末余额",
                lead_book_balance(row.values),
                row=row.source_row,
                amount_type="Lead余额",
            )
        )
    return _evidence_item(
        sheet=lead.source_sheet,
        section="K.00 Lead 固定资产余额行",
        location=_rows_location(rows),
        identified_by=_identified_by(
            sheet=lead.source_sheet,
            section="movement_rows",
            keywords=["Lead", "原值", "累计折旧", "减值准备", "净值"],
            rows=rows,
        ),
        key_columns=["科目名称", "期初审定数", "期末审定数", "索引号"],
        values_read=values,
    )


def _rollforward_totals_evidence_item(rollforward: RollforwardSheetDataset) -> dict:
    values = []
    for field_key, value in (rollforward.ending_totals or {}).items():
        if field_key in _HOW_FIELD_LABELS:
            values.append(
                _value_read(
                    _HOW_FIELD_LABELS.get(field_key, field_key) + " K.01期末汇总",
                    value,
                    row=rollforward.total_row,
                    amount_type="K.01后推汇总",
                )
            )
    missing = [] if values else ["未识别到 K.01 可比对的期末汇总金额"]
    return _evidence_item(
        sheet=rollforward.source_sheet,
        section="K.01 后推汇总金额",
        location=_rows_location([rollforward.total_row]),
        identified_by=_identified_by(
            sheet=rollforward.source_sheet,
            section="ending_totals/opening_totals",
            keywords=["K.01", "后推", "合计", "原值", "累计折旧", "净值"],
            rows=[rollforward.total_row],
        ),
        key_columns=["原值", "累计折旧", "减值准备", "净值"],
        values_read=values,
        missing_data=missing,
    )


def _direct_differences(
    lead: LeadSheetDataset,
    rollforward: RollforwardSheetDataset,
    *,
    period: str,
) -> tuple[dict[str, object], int]:
    totals = rollforward.opening_totals if period == "opening" else rollforward.ending_totals
    value_role = "py_audited" if period == "opening" else "audited_ending"
    differences: dict[str, object] = {}
    compared_fields = 0
    for row in lead.movement_rows:
        field_key = movement_field_key(row.account_label)
        if field_key is None:
            continue
        lead_amt = (
            parse_threshold_amount(row.values.get(value_role))
            if period == "opening"
            else lead_book_balance(row.values)
        )
        rf_amt = totals.get(field_key)
        if lead_amt is None or rf_amt is None:
            continue
        compared_fields += 1
        if not amounts_close(lead_amt, rf_amt, ref=max(abs(lead_amt), abs(rf_amt))):
            differences[field_key] = lead_amt - rf_amt
    return differences, compared_fields


def _rf_sheet(rollforward: RollforwardSheetDataset | None) -> str | None:
    return rollforward.source_sheet if rollforward and rollforward.source_sheet else None

def check_lead_rollforward_tb_reconciliation(
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    """引导表期末账面数与 K.01 后推 TB 合计一致。"""
    if lead is None or not lead.source_sheet:
        return []
    if rollforward is None or not (rollforward.ending_totals or rollforward.opening_totals):
        return []

    issues: list[QcIssue] = []
    k01_check_issues = _check_from_k01_check_column(rollforward)
    if k01_check_issues is not None:
        issues.extend(k01_check_issues)
    else:
        issues.extend(_direct_period_check(lead, rollforward, period="ending"))

    if any(
        binding.period_role == RollforwardPeriodRole.OPENING
        for binding in rollforward.amount_column_bindings
    ):
        issues.extend(_direct_period_check(lead, rollforward, period="opening"))
    return issues


def _direct_period_check(
    lead: LeadSheetDataset,
    rollforward: RollforwardSheetDataset,
    *,
    period: str,
) -> list[QcIssue]:
    totals = rollforward.opening_totals if period == "opening" else rollforward.ending_totals
    value_role = "py_audited" if period == "opening" else "audited_ending"
    differences: dict[str, tuple[object, int | None]] = {}
    for row in lead.movement_rows:
        field_key = movement_field_key(row.account_label)
        if field_key is None:
            continue
        lead_amt = (
            parse_threshold_amount(row.values.get(value_role))
            if period == "opening"
            else lead_book_balance(row.values)
        )
        rf_amt = totals.get(field_key)
        if lead_amt is None or rf_amt is None:
            continue
        if not amounts_close(lead_amt, rf_amt, ref=max(abs(lead_amt), abs(rf_amt))):
            differences[field_key] = (lead_amt - rf_amt, row.source_row)
    return _group_period_differences(
        differences,
        period_label="期初" if period == "opening" else "期末",
        source_sheet=lead.source_sheet,
        procedure_code="K.00",
    )


def _group_period_differences(
    differences: dict[str, tuple[object, int | None]],
    *,
    period_label: str,
    source_sheet: str,
    procedure_code: str,
) -> list[QcIssue]:
    if not differences:
        return []
    component_keys = [
        key
        for key in ("original_value", "accumulated_depreciation", "impairment_provision")
        if key in differences
    ]
    report_keys = component_keys or ["net_value"]
    parts = [
        f"{_FIELD_LABELS.get(key, key)}差异={differences[key][0]}"
        for key in report_keys
    ]
    if component_keys and "net_value" in differences:
        parts.append(f"并导致净值差异={differences['net_value'][0]}")
    first_key = report_keys[0]
    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field=f"{period_label}|{'|'.join(report_keys)}",
            severity=Severity.FAIL,
            message=f"Lead 与 K.01 {period_label}数不一致：" + "；".join(parts),
            suggestion=f"请核对 Lead 与 K.01 {period_label}四项金额的链接、取数公式及差异原因。",
            procedure_code=procedure_code,
            source_sheet=source_sheet,
            source_row=differences[first_key][1],
        )
    ]
