"""addition_rollforward_reconciliation 与 K.01 购置行 ingest 单测。"""

from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadBasicInfoField, LeadSheetDataset, MaterialityCapture
from ingest.models import AssetRecord, FieldMapping, RollforwardPeriodRole
from ingest.records import FaListDataset
from ingest.rollforward_sheet import (
    MovementTransactionAmount,
    RollforwardSheetDataset,
    get_movement_transaction_amount,
    parse_rollforward_rows,
)
from rules.addition_rollforward_reconciliation import check_addition_rollforward_reconciliation
from rules.models import Severity


def _addition_dataset(records: list[AssetRecord]) -> FaListDataset:
    return FaListDataset(
        source_file="test.xlsx",
        source_sheet="新增清单",
        mapped_fields=[
            FieldMapping("asset_id", "固定资产编号", 1),
            FieldMapping("original_value", "原值", 2),
            FieldMapping("addition_method", "新增方式", 3),
        ],
        records=records,
    )


def _lead_with_sad(value: str = "5") -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=[
            LeadBasicInfoField(
                field_key="sad",
                label="名义金额 (SAD)",
                value=value,
                source_row=3,
                source_col=2,
            )
        ],
        materiality=[
            MaterialityCapture(
                field_key="sad",
                label="名义金额 (SAD)",
                workpaper_value=value,
                source_row=3,
                source_col_workpaper=2,
            )
        ],
    )


def test_rollforward_ingest_extracts_purchase_transaction_row():
    rows: list[tuple] = [()] * 40
    rows[10] = ("", "变动", "原值变动金额", "本年VS上年", 0, 0, 0, 100)
    rows[11] = ("", "购置", 50, 0, 0)
    rows[12] = ("", "在建工程转入", 50, 0, 0)

    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    amount, row_no = get_movement_transaction_amount(
        rf,
        transaction_key="purchase",
        measure="original_value",
    )
    assert amount == Decimal("50")
    assert row_no == 12


def test_rollforward_ingest_sums_matrix_category_purchase_amounts():
    """SOP 表1 矩阵：购置行按各类别审定数汇总，而非取首个类别金额。"""
    rows: list[tuple] = [()] * 20
    rows[9] = ("", "表1", "", "", "固定资产类别", "", "办公设备", "", "电子设备", "", "机器设备")
    rows[12] = (
        "",
        "",
        "购置",
        "K.02.1",
        0,
        "",
        0,
        Decimal("25746.67"),
        "",
        Decimal("25746.67"),
        Decimal("774300"),
        "",
    )

    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    amount, _ = get_movement_transaction_amount(
        rf,
        transaction_key="purchase",
        measure="original_value",
    )
    assert amount == Decimal("25746.67") + Decimal("774300")


def test_reconciliation_pass_when_amounts_match():
    addition = _addition_dataset(
        [
            AssetRecord(
                source_row=2,
                asset_id="FA-TEST-001",
                original_value="100",
                addition_method="购置",
            ),
            AssetRecord(
                source_row=3,
                asset_id="FA-TEST-002",
                original_value="50",
                addition_method="采购",
            ),
            AssetRecord(
                source_row=4,
                asset_id="FA-TEST-003",
                original_value="999",
                addition_method="在建工程转入",
            ),
        ]
    )
    rf = RollforwardSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        movement_transactions=[
            MovementTransactionAmount(
                transaction_key="purchase",
                transaction_label="购置",
                measure="original_value",
                amount=Decimal("150"),
                source_row=11,
            )
        ],
    )
    assert not check_addition_rollforward_reconciliation(addition, rollforward=rf)


def test_reconciliation_warn_when_mismatch_within_sad():
    addition = _addition_dataset(
        [
            AssetRecord(
                source_row=2,
                asset_id="FA-TEST-001",
                original_value="100",
                addition_method="购置",
            )
        ]
    )
    rf = RollforwardSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        movement_transactions=[
            MovementTransactionAmount(
                transaction_key="purchase",
                transaction_label="购置",
                measure="original_value",
                amount=Decimal("103"),
                source_row=11,
            )
        ],
    )
    issues = check_addition_rollforward_reconciliation(
        addition,
        rollforward=rf,
        lead=_lead_with_sad("10"),
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARN
    assert "差异=3" in issues[0].message
    assert "超过 SAD" not in issues[0].message


def test_reconciliation_warn_when_mismatch_over_sad():
    addition = _addition_dataset(
        [
            AssetRecord(
                source_row=2,
                asset_id="FA-TEST-001",
                original_value="100",
                addition_method="购置",
            )
        ]
    )
    rf = RollforwardSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        movement_transactions=[
            MovementTransactionAmount(
                transaction_key="purchase",
                transaction_label="购置",
                measure="original_value",
                amount=Decimal("200"),
                source_row=11,
            )
        ],
    )
    issues = check_addition_rollforward_reconciliation(
        addition,
        rollforward=rf,
        lead=_lead_with_sad("5"),
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARN
    assert "超过 SAD" in issues[0].message


def test_reconciliation_need_review_when_purchase_row_missing():
    addition = _addition_dataset(
        [
            AssetRecord(
                source_row=2,
                asset_id="FA-TEST-001",
                original_value="100",
                addition_method="购置",
            )
        ]
    )
    rf = RollforwardSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        has_movement_rows=True,
    )
    issues = check_addition_rollforward_reconciliation(addition, rollforward=rf)
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert "购置" in issues[0].message
