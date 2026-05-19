from ingest.models import AssetRecord
from rules.fa_list_required_fields import check_fa_list_required_fields
from rules.models import ColumnContext, Severity


def test_sheet_missing_core_columns():
    ctx = ColumnContext(mapped_fields={"asset_id"})
    issues = check_fa_list_required_fields([], ctx)
    fields = {i.field for i in issues}
    assert "original_value" in fields
    assert any(i.severity == Severity.FAIL for i in issues)


def test_row_missing_recommended_warn():
    ctx = ColumnContext(
        mapped_fields={
            "asset_id",
            "asset_name",
            "original_value",
            "accumulated_depreciation",
            "net_value",
            "asset_category",
            "start_date",
            "useful_life_months",
            "salvage_rate",
        }
    )
    record = AssetRecord(
        source_row=2,
        asset_id="FA-TEST-001",
        asset_name="测试",
        original_value="1000",
        accumulated_depreciation="100",
        net_value="900",
        asset_category="",
        start_date="2024-01-01",
        useful_life_months="",
        salvage_rate="0.05",
    )
    issues = check_fa_list_required_fields([record], ctx)
    assert any(
        i.field == "asset_category" and i.severity == Severity.WARN for i in issues
    )
