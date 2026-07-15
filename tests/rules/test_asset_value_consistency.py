from decimal import Decimal

from ingest.models import AssetRecord
from rules.asset_value_consistency import check_asset_value_consistency
from rules.models import ColumnContext, Severity


def test_amount_mismatch_fail():
    ctx = ColumnContext(
        mapped_fields={"original_value", "accumulated_depreciation", "impairment_provision", "net_value"}
    )
    record = AssetRecord(
        source_row=2,
        asset_id="FA-TEST-003",
        original_value="5000",
        accumulated_depreciation="1000",
        impairment_provision="0",
        net_value="5000",
    )
    issues = check_asset_value_consistency([record], ctx)
    assert len(issues) == 1
    assert issues[0].severity == Severity.FAIL


def test_non_numeric_need_review():
    ctx = ColumnContext(
        mapped_fields={"original_value", "accumulated_depreciation", "net_value"}
    )
    record = AssetRecord(
        source_row=2,
        asset_name="测试",
        original_value="待定",
        accumulated_depreciation="50",
        net_value="950",
    )
    issues = check_asset_value_consistency([record], ctx)
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW


def test_consistent_amounts_pass():
    ctx = ColumnContext(
        mapped_fields={
            "original_value",
            "accumulated_depreciation",
            "net_value",
            "impairment_provision",
        }
    )
    record = AssetRecord(
        source_row=2,
        asset_id="FA-TEST-001",
        original_value="10000",
        accumulated_depreciation="3000",
        impairment_provision="0",
        net_value="7000",
    )
    issues = check_asset_value_consistency([record], ctx, tolerance=Decimal("0.01"))
    assert issues == []


def test_consistent_amounts_pass_when_accumulated_depreciation_is_credit_negative():
    ctx = ColumnContext(
        mapped_fields={
            "original_value",
            "accumulated_depreciation",
            "net_value",
            "impairment_provision",
        }
    )
    record = AssetRecord(
        source_row=2,
        asset_id="FA-TEST-001",
        original_value="10000",
        accumulated_depreciation="-3000",
        impairment_provision="0",
        net_value="7000",
    )
    issues = check_asset_value_consistency([record], ctx, tolerance=Decimal("0.01"))
    assert issues == []
