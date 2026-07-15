from ingest.models import AssetRecord
from rules.models import ColumnContext, Severity
from rules.useful_life_positive import check_useful_life_positive


def test_years_to_months():
    ctx = ColumnContext(mapped_fields={"useful_life_months", "asset_id"})
    record = AssetRecord(source_row=2, asset_id="FA-TEST-001", useful_life_months="5年")
    assert check_useful_life_positive([record], ctx) == []


def test_zero_months_fail():
    ctx = ColumnContext(mapped_fields={"useful_life_months", "asset_id"})
    record = AssetRecord(source_row=2, asset_id="FA-TEST-001", useful_life_months="0")
    issues = check_useful_life_positive([record], ctx)
    assert issues[0].severity == Severity.FAIL


def test_negative_months_and_negative_years_preserve_sign_and_fail():
    ctx = ColumnContext(
        mapped_fields={"useful_life_months", "asset_id"},
        mapped_headers={"useful_life_months": "使用寿命（月）"},
    )
    records = [
        AssetRecord(source_row=2, asset_id="A", useful_life_months="-12"),
        AssetRecord(source_row=3, asset_id="B", useful_life_months="-5年"),
    ]

    issues = check_useful_life_positive(records, ctx)

    assert len(issues) == 2
    assert all(issue.severity == Severity.FAIL for issue in issues)
