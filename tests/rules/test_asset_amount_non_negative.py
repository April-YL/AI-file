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


def test_negative_impairment_is_allowed_and_mixed_contra_signs_emit_one_review():
    ctx = ColumnContext(
        mapped_fields={"accumulated_depreciation", "impairment_provision", "asset_id"}
    )
    records = [
        AssetRecord(asset_id="A", accumulated_depreciation="-10", impairment_provision="-2"),
        AssetRecord(asset_id="B", accumulated_depreciation="10", impairment_provision="2"),
    ]

    issues = check_asset_amount_non_negative(records, ctx)

    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].source_row is None
