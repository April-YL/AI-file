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
        return {"path": "data_insufficient", "inputs": [], "checks": [], "notes": ["lead_missing"]}
    inputs = [
        {
            "source_sheet": lead.source_sheet,
            "section": "movement_rows",
            "field": "lead_book_balance",
            "row": None,
            "column": None,
            "range": None,
        }
    ]
    if rollforward is None or not (rollforward.ending_totals or rollforward.opening_totals):
        return {
            "path": "data_insufficient",
            "inputs": inputs,
            "checks": [],
            "notes": ["rollforward_totals_missing"],
        }

    checks = getattr(rollforward, "table1_check_values", None) or {}
    if checks:
        path = "primary"
        rows = getattr(rollforward, "table1_check_rows", None) or {}
        first_row = next((row for row in rows.values() if row), None)
        inputs.append(
            {
                "source_sheet": rollforward.source_sheet,
                "section": "table1_check_column",
                "field": "table1_check_values",
                "row": first_row,
                "column": None,
                "range": None,
            }
        )
        non_zero = [
            value
            for value in checks.values()
            if value is not None and not amounts_close(value, 0, ref=max(abs(value), 1))
        ]
        checks_out = [
            {
                "name": "k01_check_column_difference",
                "left_label": "non_zero_check_count",
                "left_value": str(len(non_zero)),
                "operator": "=",
                "right_label": "expected_non_zero_count",
                "right_value": "0",
                "result": "triggered" if non_zero else "passed",
            }
        ]
        notes = ["used_k01_check_column"]
    else:
        path = "fallback"
        inputs.append(
            {
                "source_sheet": rollforward.source_sheet,
                "section": "rollforward_totals",
                "field": "opening_totals/ending_totals",
                "row": rollforward.total_row,
                "column": None,
                "range": None,
            }
        )
        compared_fields = 0
        for row in lead.movement_rows:
            field_key = movement_field_key(row.account_label)
            if field_key and field_key in rollforward.ending_totals:
                compared_fields += 1
        checks_out = [
            {
                "name": "direct_lead_k01_compared_fields",
                "left_label": "compared_fields",
                "left_value": str(compared_fields),
                "operator": "exists",
                "right_label": "direct_check_fields",
                "right_value": None,
                "result": "passed" if compared_fields else "data_insufficient",
            }
        ]
        notes = ["k01_check_column_not_available"]
    return {"path": path, "inputs": inputs[:8], "checks": checks_out[:8], "notes": notes[:5]}

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
