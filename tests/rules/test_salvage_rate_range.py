from ingest.models import AssetRecord
from rules.models import ColumnContext, Severity
from rules.salvage_rate_range import check_salvage_rate_range


def test_percent_input_warn():
    ctx = ColumnContext(mapped_fields={"salvage_rate", "asset_id"})
    record = AssetRecord(source_row=2, asset_id="FA-TEST-001", salvage_rate="5%")
    issues = check_salvage_rate_range([record], ctx)
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARN


def test_out_of_range_fail():
    ctx = ColumnContext(mapped_fields={"salvage_rate", "asset_id"})
    record = AssetRecord(source_row=2, asset_id="FA-TEST-001", salvage_rate="150%")
    issues = check_salvage_rate_range([record], ctx)
    assert issues[0].severity == Severity.FAIL
