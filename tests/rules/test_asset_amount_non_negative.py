from ingest.models import AssetRecord
from rules.asset_amount_non_negative import check_asset_amount_non_negative
from rules.models import ColumnContext, Severity


def test_negative_net_fail():
    ctx = ColumnContext(mapped_fields={"net_value", "asset_id"})
    record = AssetRecord(source_row=2, asset_id="FA-TEST-001", net_value="-100")
    issues = check_asset_amount_non_negative([record], ctx)
    assert len(issues) == 1
    assert issues[0].severity == Severity.FAIL


def test_negative_accumulated_depreciation_is_allowed_for_credit_presentation():
    ctx = ColumnContext(mapped_fields={"accumulated_depreciation", "asset_id"})
    record = AssetRecord(
        source_row=2,
        asset_id="FA-TEST-001",
        accumulated_depreciation="-100",
    )
    assert check_asset_amount_non_negative([record], ctx) == []
