from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_required_fields"

# 与 docs/planning/lead-qc-rules.md 模块 1 一致；PM 由 AE-001 摘录
LEAD_REQUIRED_FIELD_KEYS: tuple[str, ...] = (
    "client_name",
    "period_end",
    "analysis_date",
    "te",
    "sad",
    "gaap",
    "currency",
)

_FIELD_LABELS: dict[str, str] = {
    "client_name": "客户名称",
    "period_end": "期末",
    "analysis_date": "分析日期",
    "te": "TE（可容忍误差）",
    "sad": "SAD（名义金额）",
    "gaap": "适用会计准则",
    "currency": "记账本位币",
}


def check_lead_required_fields(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """K.00 基准信息必填：客户名称、期末、分析日期、TE、SAD、准则、币种。"""
    if lead is None or not lead.source_sheet:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=None,
                severity=Severity.FAIL,
                message="未找到 K.00 Lead Sheet，无法检查基准信息完整性",
                suggestion="请确认底稿含 Lead 表并完成 sheet 分类",
                procedure_code="K.00",
                source_sheet="K.00 Lead Sheet",
            )
        ]

    values = field_values(lead)
    fields_by_key = {f.field_key: f for f in lead.basic_info_fields}
    issues: list[QcIssue] = []
    for key in LEAD_REQUIRED_FIELD_KEYS:
        label = _FIELD_LABELS.get(key, key)
        raw = values.get(key)
        field = fields_by_key.get(key)
        if is_blank(raw):
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=key,
                    severity=Severity.FAIL,
                    message=f"Lead 基准信息缺少必填项：{label}",
                    suggestion=f"在 Lead 表补充{label}并更新至本审计期间",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                    source_row=field.source_row if field else None,
                )
            )
    return issues
