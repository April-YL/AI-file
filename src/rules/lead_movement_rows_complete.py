from __future__ import annotations

from ingest.lead_sheet import LeadMovementRow, LeadSheetDataset
from ingest.lead_sheet_blocks import LeadBlockKind
from rules.lead_common import A3_NET_VALUE_LABEL, _REQUIRED_MOVEMENT_LABELS
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_movement_rows_complete"

_CORE_ROLES = ("sheet_ref", "audited_ending", "py_audited")
_OPTIONAL_ROLES = ("movement_amount", "movement_pct", "book_balance")


def _movement_field_value(row: LeadMovementRow, role: str) -> str | None:
    if role == "sheet_ref":
        return row.sheet_ref
    return row.values.get(role)


def _row_requires_sheet_ref(row: LeadMovementRow) -> bool:
    """净值由前三行勾稽，不要求单独填索引号。"""
    label = row.account_label or ""
    return A3_NET_VALUE_LABEL not in label


def check_lead_movement_rows_complete(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """两期引导主表：四行账户 + 核心列存在。"""
    if lead is None or not lead.source_sheet:
        return []

    if lead.block(LeadBlockKind.MOVEMENT_TABLE) is None and not lead.movement_rows:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="movement_table",
                severity=Severity.WARN,
                message="未识别 Lead 两期引导主表",
                suggestion="按模板维护原值、累计折旧、减值准备、净值四行",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    issues: list[QcIssue] = []
    present_labels = {r.account_label for r in lead.movement_rows}
    for label in _REQUIRED_MOVEMENT_LABELS:
        if not any(label in p for p in present_labels):
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=f"movement:{label}",
                    severity=Severity.FAIL,
                    message=f"引导主表缺少账户行：{label}",
                    suggestion=f"补充{label}行及期初/期末、变动列",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                )
            )

    bound_roles = {b.role for b in lead.movement_bindings}
    for role in _CORE_ROLES:
        if role not in bound_roles:
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=role,
                    severity=Severity.WARN,
                    message=f"引导主表未映射核心列：{role}",
                    suggestion="确认表头含索引号、期末审定数、上期末审定数等列",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                )
            )

    for row in lead.movement_rows:
        if row.account_label not in _REQUIRED_MOVEMENT_LABELS and not any(
            lbl in row.account_label for lbl in _REQUIRED_MOVEMENT_LABELS
        ):
            continue
        for role in _CORE_ROLES:
            if role not in bound_roles:
                continue
            if role == "sheet_ref" and not _row_requires_sheet_ref(row):
                continue
            if is_blank(_movement_field_value(row, role)):
                issues.append(
                    QcIssue(
                        asset_id=None,
                        rule_id=RULE_ID,
                        field=f"{row.account_label}|{role}",
                        severity=Severity.WARN,
                        message=f"「{row.account_label}」行缺少 {role} 值",
                        suggestion="补充该列或确认 link 公式",
                        procedure_code="K.00",
                        source_sheet=lead.source_sheet,
                        source_row=row.source_row,
                    )
                )

    return issues
