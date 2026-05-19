from ingest.models import AssetRecord
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
