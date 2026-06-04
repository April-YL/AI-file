from ingest.models import AssetRecord, FieldMapping
from ingest.records import FaListDataset
from rules.addition_runner import run_addition_rules
from rules.addition_required_fields import check_addition_required_fields
from rules.addition_population_homogeneity import check_addition_population_homogeneity
from rules.models import ColumnContext, Severity


def _ctx(mapped: set[str]) -> ColumnContext:
    return ColumnContext(
        mapped_fields=mapped,
        source_sheet="新增清单",
        procedure_code="K.02.1",
    )


def test_addition_required_fields_reports_missing_sheet_columns():
    issues = check_addition_required_fields(
        [],
        _ctx({"asset_id", "asset_name", "original_value"}),
    )
    fields = {i.field for i in issues}
    assert {"asset_category", "start_date", "addition_method"} <= fields
    assert all(i.severity == Severity.FAIL for i in issues)


def test_addition_required_fields_reports_blank_row_values():
    record = AssetRecord(
        source_row=5,
        asset_id="FA-TEST-001",
        asset_name="设备A",
        asset_category="机器设备",
        start_date="",
        original_value="1000",
        addition_method="购置",
    )
    issues = check_addition_required_fields(
        [record],
        _ctx(
            {
                "asset_id",
                "asset_name",
                "asset_category",
                "start_date",
                "original_value",
                "addition_method",
            }
        ),
    )
    assert len(issues) == 1
    assert issues[0].field == "start_date"
    assert issues[0].source_row == 5


def test_addition_population_homogeneity_flags_non_purchase_methods():
    records = [
        AssetRecord(source_row=2, asset_id="FA-TEST-001", original_value="100", addition_method="购置"),
        AssetRecord(source_row=3, asset_id="FA-TEST-002", original_value="200", addition_method="在建工程转入"),
        AssetRecord(source_row=4, asset_id="FA-TEST-003", original_value="300", addition_method="企业合并增加"),
    ]
    issues = check_addition_population_homogeneity(
        records,
        _ctx({"asset_id", "original_value", "addition_method"}),
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert "在建工程转入" in issues[0].message
    assert "企业合并增加" in issues[0].message


def test_addition_runner_uses_dataset_metadata():
    dataset = FaListDataset(
        source_file="dummy.xlsx",
        source_sheet="新增清单",
        mapped_fields=[
            FieldMapping("asset_id", "固定资产编号", 1),
            FieldMapping("asset_name", "固定资产名称", 2),
            FieldMapping("asset_category", "固定资产类别", 3),
            FieldMapping("start_date", "入账开始日期", 4),
            FieldMapping("original_value", "原值", 5),
            FieldMapping("addition_method", "新增方式", 6),
        ],
        records=[
            AssetRecord(
                source_row=2,
                asset_id="FA-TEST-001",
                asset_name="设备A",
                asset_category="机器设备",
                start_date="2024-01-01",
                original_value="1000",
                addition_method="在建工程转入",
            )
        ],
    )
    issues = run_addition_rules(dataset)
    assert {i.rule_id for i in issues} == {
        "addition_population_homogeneity",
        "addition_rollforward_reconciliation",
    }
    recon = next(i for i in issues if i.rule_id == "addition_rollforward_reconciliation")
    assert recon.severity == Severity.NEED_REVIEW
