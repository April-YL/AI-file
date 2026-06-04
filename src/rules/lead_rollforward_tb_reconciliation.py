from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.lead_common import (
    amounts_close,
    lead_book_balance,
    movement_field_key,
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

    issues: list[QcIssue] = []
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
        label = _FIELD_LABELS.get(field_key, field_key)
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=f"table1_check|{field_key}",
                severity=Severity.FAIL,
                message=(
                    f"K.01 表1 CHECK 显示「{label}」与 Lead 不一致，"
                    f"差异={diff}"
                ),
                suggestion="请在 K.01 表1 CHECK 列核对后推表与 Lead 的链接和取数公式。",
                procedure_code="K.01",
                source_sheet=rollforward.source_sheet,
                source_row=rows.get(field_key),
            )
        )
    return issues


def check_lead_rollforward_tb_reconciliation(
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    """引导表期末账面数与 K.01 后推 TB 合计一致。"""
    if lead is None or not lead.source_sheet:
        return []
    if rollforward is None or not rollforward.ending_totals:
        return []

    k01_check_issues = _check_from_k01_check_column(rollforward)
    if k01_check_issues is not None:
        return k01_check_issues

    issues: list[QcIssue] = []
    for row in lead.movement_rows:
        field_key = movement_field_key(row.account_label)
        if field_key is None:
            continue
        lead_amt = lead_book_balance(row.values)
        rf_amt = rollforward.ending_totals.get(field_key)
        if lead_amt is None or rf_amt is None:
            continue
        if not amounts_close(lead_amt, rf_amt, ref=max(abs(lead_amt), abs(rf_amt))):
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=f"{field_key}|{row.account_label}",
                    severity=Severity.FAIL,
                    message=(
                        f"Lead「{row.account_label}」期末数（{lead_amt}）与 K.01 后推"
                        f"（{rf_amt}）不一致"
                    ),
                    suggestion="核对引导表 link 与后推 TB 列公式",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                    source_row=row.source_row,
                )
            )
    return issues
