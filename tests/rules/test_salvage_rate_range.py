from ingest.models import (
    AssetRecord,
    FaListSalvageBasis,
    FaListSalvageMode,
)
from rules.models import ColumnContext, Severity
from rules.salvage_rate_range import check_salvage_rate_range


def test_percent_input_is_valid_without_noise():
    ctx = ColumnContext(mapped_fields={"salvage_rate", "asset_id"})
    record = AssetRecord(source_row=2, asset_id="FA-TEST-001", salvage_rate="5%")
    issues = check_salvage_rate_range([record], ctx)
    assert issues == []


def test_out_of_range_fail():
    ctx = ColumnContext(mapped_fields={"salvage_rate", "asset_id"})
    record = AssetRecord(source_row=2, asset_id="FA-TEST-001", salvage_rate="150%")
    issues = check_salvage_rate_range([record], ctx)
    assert issues[0].severity == Severity.FAIL


def test_salvage_value_is_derived_against_original_value():
    ctx = ColumnContext(mapped_fields={"salvage_value", "original_value", "asset_id"})
    basis = FaListSalvageBasis(
        mode=FaListSalvageMode.DERIVED_FROM_VALUE,
        value_column=3,
    )
    record = AssetRecord(
        source_row=2,
        asset_id="FA-TEST-001",
        original_value="100",
        salvage_value="5",
    )

    assert check_salvage_rate_range([record], ctx, basis) == []


def test_explicit_rate_and_value_are_cross_checked_without_noise_when_consistent():
    ctx = ColumnContext(
        mapped_fields={"salvage_rate", "salvage_value", "original_value", "asset_id"}
    )
    basis = FaListSalvageBasis(
        mode=FaListSalvageMode.RATE_AND_VALUE,
        rate_column=2,
        value_column=3,
    )
    record = AssetRecord(
        source_row=2,
        asset_id="FA-TEST-001",
        original_value="100",
        salvage_value="5",
        salvage_rate="5%",
    )

    assert check_salvage_rate_range([record], ctx, basis) == []


def test_rate_and_value_mismatches_are_aggregated_to_one_review():
    ctx = ColumnContext(
        mapped_fields={"salvage_rate", "salvage_value", "original_value", "asset_id"}
    )
    basis = FaListSalvageBasis(
        mode=FaListSalvageMode.RATE_AND_VALUE,
        rate_column=2,
        value_column=3,
    )
    records = [
        AssetRecord(source_row=2, asset_id="FA-TEST-001", original_value="100", salvage_value="10", salvage_rate="5%"),
        AssetRecord(source_row=3, asset_id="FA-TEST-002", original_value="200", salvage_value="20", salvage_rate="5%"),
    ]

    issues = check_salvage_rate_range(records, ctx, basis)

    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert "共 2 行" in issues[0].message
    assert issues[0].source_row == 2
