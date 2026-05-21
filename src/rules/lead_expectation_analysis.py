from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.lead_sheet_blocks import LeadBlockKind
from rules.models import QcIssue, Severity

RULE_ID = "lead_expectation_analysis"


def check_lead_expectation_analysis(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """预期分析块与波动门槛（金额、比例）应可识别。"""
    if lead is None or not lead.source_sheet:
        return []

    has_block = lead.block(LeadBlockKind.EXPECTATION) is not None
    has_expectations = len(lead.expectations) > 0
    vol = lead.volatility

    issues: list[QcIssue] = []
    if not has_block and not has_expectations and vol is None:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="expectation",
                severity=Severity.WARN,
                message="未识别 Lead 预期分析 / 波动门槛区块",
                suggestion="按模板维护账户变更预期与波动幅度金额、比例",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        )
        return issues

    if not has_expectations:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="expectation",
                severity=Severity.WARN,
                message="预期分析区未摘录到账户变更预期行",
                suggestion="填写新增、减少、折旧等账户变更预期（不要求 7 行均有文字）",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        )

    if vol is None or (not vol.amount and not vol.percent):
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="volatility",
                severity=Severity.WARN,
                message="未识别波动幅度金额或比例门槛",
                suggestion="维护波动幅度（CNY）与波动幅度（%）阈值",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        )

    return issues
