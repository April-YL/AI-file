from ingest.models import AssetRecord, FaListIdentityBasis, FaListIdentityScope
from rules.models import ColumnContext, Severity
from rules.unique_asset_id import check_unique_asset_id


def test_duplicate_asset_id_fail():
    ctx = ColumnContext(mapped_fields={"asset_id"})
    records = [
        AssetRecord(source_row=2, asset_id="FA-TEST-001"),
        AssetRecord(source_row=3, asset_id="FA-TEST-001"),
    ]
    issues = check_unique_asset_id(records, ctx)
    assert len(issues) == 2
    assert all(i.severity == Severity.FAIL for i in issues)


def test_no_asset_id_column_need_review():
    ctx = ColumnContext(mapped_fields={"asset_name"})
    issues = check_unique_asset_id(
        [AssetRecord(source_row=2, asset_name="测试")],
        ctx,
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW


def test_group_scope_uses_entity_and_asset_id_composite_key():
    ctx = ColumnContext(mapped_fields={"entity_name", "asset_id"})
    records = [
        AssetRecord(source_row=2, entity_name="A公司", asset_id="001"),
        AssetRecord(source_row=3, entity_name="B公司", asset_id="001"),
        AssetRecord(source_row=4, entity_name="A公司", asset_id="001"),
    ]
    basis = FaListIdentityBasis(scope=FaListIdentityScope.ENTITY_ASSET_ID)

    issues = check_unique_asset_id(records, ctx, basis)

    assert {issue.source_row for issue in issues} == {2, 4}
