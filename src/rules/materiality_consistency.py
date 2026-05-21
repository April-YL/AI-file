from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from rules.models import QcIssue, Severity

RULE_ID = "materiality_consistency"


def check_materiality_consistency(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """AE-001：摘录 PM/TE/SAD 供人工与 Canvas 核对；无法自动比对。"""
    if lead is None or not lead.source_sheet:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=None,
                severity=Severity.NEED_REVIEW,
                message="未找到 K.00 Lead Sheet，无法摘录 PM/TE/SAD",
                suggestion="请确认底稿含 Lead 表，或见报告 manual_review_sections.AE-001 手工填写",
                procedure_code="K.00",
                source_sheet="K.00 Lead Sheet",
            )
        ]

    issues: list[QcIssue] = []
    # TE/SAD 缺项由 lead_required_fields 判定 FAIL；此处仅摘录 + Canvas 人工核对
    issues.append(
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field="pm|te|sad",
            severity=Severity.NEED_REVIEW,
            message="PM/TE/SAD 须与 Canvas 最终结果一致（见报告摘录区 AE-001）",
            suggestion="对照报告 manual_review_sections 中 AE-001 底稿值与 Canvas 列完成人工核对",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
        )
    )
    return issues
