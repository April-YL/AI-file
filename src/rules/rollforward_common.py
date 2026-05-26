"""K.01 后推规则共用常量与 L1 列完整性判定。"""

from __future__ import annotations

from ingest.models import RollforwardLayoutProfile, RollforwardPeriodRole
from ingest.rollforward_sheet import RollforwardSheetDataset

REQUIRED_MEASURES: tuple[str, ...] = (
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "net_value",
)

_MEASURE_LABELS: dict[str, str] = {
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧",
    "impairment_provision": "减值准备",
    "net_value": "净值",
}

L1_LAYOUTS: frozenset[RollforwardLayoutProfile] = frozenset(
    {
        RollforwardLayoutProfile.CATEGORY_DUAL_PERIOD,
        RollforwardLayoutProfile.HYBRID,
        RollforwardLayoutProfile.SOP_BKD_MATRIX,
    }
)


def measures_present(rf: RollforwardSheetDataset) -> set[str]:
    """bindings 或 ending_totals 中出现的口径。"""
    found: set[str] = set()
    for b in rf.amount_column_bindings:
        found.add(b.measure)
    for key, val in rf.ending_totals.items():
        if key in REQUIRED_MEASURES and val is not None:
            found.add(key)
    for key, val in rf.opening_totals.items():
        if key in REQUIRED_MEASURES and val is not None:
            found.add(key)
    return found


def has_opening_signal(rf: RollforwardSheetDataset) -> bool:
    if any(v is not None for v in rf.opening_totals.values()):
        return True
    if any(b.period_role == RollforwardPeriodRole.OPENING for b in rf.amount_column_bindings):
        return True
    return False


def has_ending_signal(rf: RollforwardSheetDataset) -> bool:
    if any(v is not None for v in rf.ending_totals.values()):
        return True
    if any(b.period_role == RollforwardPeriodRole.ENDING for b in rf.amount_column_bindings):
        return True
    return False


def has_movement_signal(rf: RollforwardSheetDataset) -> bool:
    if rf.has_movement_rows:
        return True
    return any(b.period_role == RollforwardPeriodRole.MOVEMENT for b in rf.amount_column_bindings)


def missing_l1_columns(rf: RollforwardSheetDataset) -> list[str]:
    """返回 L1 未满足项的人类可读描述。"""
    gaps: list[str] = []
    present = measures_present(rf)
    for m in REQUIRED_MEASURES:
        if m not in present:
            gaps.append(f"缺少金额口径：{_MEASURE_LABELS.get(m, m)}")
    if not has_opening_signal(rf):
        gaps.append("缺少期初列或期初合计（如审2/表2/期初/年初）")
    if not has_ending_signal(rf):
        gaps.append("缺少期末列或期末合计（如审3/表3/期末/年末）")
    if not has_movement_signal(rf):
        gaps.append("缺少本期变动信息（变动金额列或购置/计提/处置等交易行）")
    return gaps


def rollforward_sheet_parseable(rf: RollforwardSheetDataset | None) -> bool:
    if rf is None or not rf.source_sheet:
        return False
    if rf.header_row is not None:
        return True
    if rf.amount_column_bindings:
        return True
    if rf.layout_profile != RollforwardLayoutProfile.UNRECOGNIZED:
        return True
    return any(v is not None for v in rf.ending_totals.values())
