from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.models import QcIssue, Severity

RULE_ID = "risk_threshold_consistency"


def check_risk_threshold_consistency(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """AE-002：摘录认定 CRA/TT 供人工核对。"""
    if lead is None or not lead.source_sheet:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=None,
                severity=Severity.NEED_REVIEW,
                message="未找到 K.00 Lead Sheet，无法摘录 CRA/TT",
                suggestion="见报告 manual_review_sections.AE-002",
                procedure_code="K.00",
                source_sheet="K.00 Lead Sheet",
            )
        ]

    if lead.layout_variant == "no_cra_te_volatility":
        return []

    issues: list[QcIssue] = []
    if not lead.cra_rows:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="cra|tt",
                severity=Severity.WARN,
                message="Lead 表未识别到认定 CRA/TT 表",
                suggestion="在 Lead 表维护认定、CRA、TT 列，或见报告 AE-002 手工填写",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        )

    issues.append(
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field="cra|tt",
            severity=Severity.NEED_REVIEW,
            message=f"各认定 CRA、TT 须人工核对（已摘录 {len(lead.cra_rows)} 行，见报告 AE-002）",
            suggestion="对照 Canvas/风险底稿完成认定级 CRA、TT 复核",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
        )
    )
    return issues
