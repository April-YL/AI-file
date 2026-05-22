from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_dates import parse_lead_date
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_analysis_date_after_period_end"


def check_lead_analysis_date_after_period_end(
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    """分析日期不得早于资产负债表日（期末）；允许与期末同日。"""
    if lead is None or not lead.source_sheet:
        return []

    values = field_values(lead)
    period_raw = values.get("period_end")
    analysis_raw = values.get("analysis_date")

    if is_blank(period_raw) or is_blank(analysis_raw):
        return []

    period = parse_lead_date(period_raw)
    analysis = parse_lead_date(analysis_raw)

    if period is None or analysis is None:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="period_end|analysis_date",
                severity=Severity.WARN,
                message="无法解析期末或分析日期，无法自动判断分析日期是否不早于期末",
                suggestion="请人工确认分析日期不早于资产负债表日",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    if analysis < period:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="analysis_date",
                severity=Severity.FAIL,
                message=(
                    f"分析日期（{analysis.isoformat()}）不得早于期末"
                    f"（{period.isoformat()}）"
                ),
                suggestion="将分析日期更新为不早于资产负债表日",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    return []
