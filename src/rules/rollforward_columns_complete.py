from __future__ import annotations

from ingest.models import RollforwardLayoutProfile
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.models import QcIssue, Severity
from rules.rollforward_common import missing_l1_columns, rollforward_sheet_parseable

RULE_ID = "rollforward_columns_complete"


def check_rollforward_columns_complete(
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    """K.01 金额列完整（M2a L1：四口径 × 期初/变动/期末可识别）。"""
    if rollforward is None or not rollforward.source_sheet:
        return []

    if not rollforward_sheet_parseable(rollforward):
        return []

    gaps = missing_l1_columns(rollforward)
    if not gaps:
        return []

    profile = rollforward.layout_profile
    if profile == RollforwardLayoutProfile.SOP_BKD_MATRIX and gaps:
        suggestion = (
            "标准 BKD 矩阵版式需账面/调整/审定子列（L2）；"
            "当前按 L1 检查未通过，请补全期初/变动/期末列或完善表1 结构"
        )
    else:
        suggestion = "请按 SOP【01】补全后推表四口径及期初、本期变动、期末列（案例库常见为审2/审3 并列）"

    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field="amount_column_bindings",
            severity=Severity.FAIL,
            message="K.01 后推表金额列不完整：" + "；".join(gaps),
            suggestion=suggestion,
            procedure_code="K.01",
            source_sheet=rollforward.source_sheet,
            source_row=rollforward.header_row,
        )
    ]
