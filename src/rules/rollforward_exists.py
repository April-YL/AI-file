from __future__ import annotations

from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.models import QcIssue, Severity
from rules.rollforward_common import rollforward_sheet_parseable

RULE_ID = "rollforward_exists"


def check_rollforward_exists(
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    """K.01 后推明细表存在且可解析主表（表头或金额列绑定）。"""
    if rollforward is None or not rollforward.source_sheet:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=None,
                severity=Severity.FAIL,
                message="未识别到 K.01 后推明细表（Agree SL to GL）",
                suggestion="请确认底稿含 K.01 工作表并完成 sheet 分类",
                procedure_code="K.01",
                source_sheet="K.01 Agree SL to GL",
            )
        ]

    if rollforward_sheet_parseable(rollforward):
        return []

    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field=None,
            severity=Severity.FAIL,
            message=f"已找到工作表「{rollforward.source_sheet}」，但无法解析后推主表（缺少表头或金额列）",
            suggestion="请按 SOP 填列表1/类别汇总区，确保含原值、累计折旧、净值等列",
            procedure_code="K.01",
            source_sheet=rollforward.source_sheet,
            source_row=rollforward.header_row,
        )
    ]
