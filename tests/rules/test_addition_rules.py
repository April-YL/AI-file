from decimal import Decimal

from ingest.addition_test_sheet import (
    AdditionAmountItem,
    AdditionExecutionPathDataset,
    AdditionParameterItem,
    AdditionSampleOutputDataset,
    AdditionSampleRow,
    AdditionTestSheetDataset,
    AdditionTestedSampleRow,
)
from ingest.lead_sheet import CraAssertionRow, LeadBasicInfoField, LeadSheetDataset
from ingest.models import AssetRecord, FieldMapping
from ingest.records import FaListDataset
from ingest.rollforward_sheet import MovementTransactionAmount, RollforwardSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
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
    assert "在建工程转入" not in issues[0].message
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
    assert {i.rule_id for i in issues} == {"addition_rollforward_reconciliation"}
    recon = next(i for i in issues if i.rule_id == "addition_rollforward_reconciliation")
    assert recon.severity == Severity.NEED_REVIEW


def test_addition_runner_records_evidence_how_for_k021_rules():
    dataset = FaListDataset(
        source_file="case.xlsx",
        source_sheet="新增清单",
        mapped_fields=[
            FieldMapping("asset_id", "固定资产编号", 1),
            FieldMapping("asset_name", "固定资产名称", 2),
            FieldMapping("asset_category", "固定资产类别", 3),
            FieldMapping("start_date", "入账日期", 4),
            FieldMapping("original_value", "新增原值", 5),
            FieldMapping("addition_method", "新增方式", 6),
        ],
        records=[
            AssetRecord(
                source_row=2,
                asset_id="FA-TEST-001",
                asset_name="设备A",
                asset_category="机器设备",
                start_date="2025-01-01",
                original_value="100",
                addition_method="购置",
            )
        ],
    )
    rollforward = RollforwardSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        movement_transactions=[
            MovementTransactionAmount(
                transaction_key="purchase",
                transaction_label="购置",
                measure="original_value",
                amount=Decimal("100"),
                source_row=12,
            )
        ],
    )
    lead = LeadSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=[
            LeadBasicInfoField(field_key="te", label="TE", value="100", source_row=8, source_col=4),
            LeadBasicInfoField(field_key="sad", label="SAD", value="5", source_row=9, source_col=4),
        ],
        cra_rows=[CraAssertionRow(assertion="存在/发生", cra="Minimal", source_row=16)],
    )
    addition_test = AdditionTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1 新增测试",
        amounts={
            "purchase_population_amount": AdditionAmountItem("购置总金额", "100", 12, 6),
            "rollforward_purchase_amount": AdditionAmountItem("Breakdown中购置金额", "100", 13, 6),
            "difference_amount": AdditionAmountItem("差异", "0", 14, 6),
        },
        tested_samples=[
            AdditionTestedSampleRow(
                source_row=34,
                sample_type="代表性样本",
                asset_id="FA-TEST-001",
                asset_name="设备A",
                original_value="100",
                evidence_amount="100",
                evidence_description="合同与发票一致",
            )
        ],
    )
    sample_output = AdditionSampleOutputDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1a 新增选样输出",
        parameters={
            "te": AdditionParameterItem("TE", "100", 15, 6),
            "covered_assertions": AdditionParameterItem("测试覆盖认定", "存在/发生", 16, 6),
            "cra": AdditionParameterItem("综合风险评估", "最低", 18, 6),
        },
        amounts={
            "sample_pool_amount": AdditionAmountItem("样本池总体金额", "100", 41, 6),
        },
        selected_samples=[
            AdditionSampleRow(
                source_row=30,
                sample_type="代表性样本",
                asset_id="FA-TEST-001",
                asset_name="设备A",
                original_value="100",
            )
        ],
    )
    execution_path = AdditionExecutionPathDataset(
        path_kind="executed",
        recognition_confidence=0.95,
        addition_list_sheet="新增清单",
        addition_test_sheet="K.02.1 新增测试",
        addition_sample_output_sheet="K.02.1a 新增选样输出",
    )
    recorder = RuleExecutionRecorder()

    issues = run_addition_rules(
        dataset,
        rollforward=rollforward,
        lead=lead,
        addition_test=addition_test,
        addition_sample_output=sample_output,
        addition_execution_path=execution_path,
        recorder=recorder,
    )

    assert issues == []
    items = {item["rule_id"]: item for item in recorder.to_ledger()["items"]}
    for rule_id in (
        "addition_required_fields",
        "addition_population_homogeneity",
        "addition_rollforward_reconciliation",
        "addition_sample_match",
        "addition_sample_pool_purchase_amount_match",
        "addition_sampling_te_cra_consistency",
        "addition_sampling_assertions_scope",
        "addition_sample_replacement_reason",
    ):
        observation = items[rule_id]["observation"]
        assert set(observation) == {
            "checked_data",
            "check_logic",
            "expected_result",
            "actual_result",
            "result_summary",
        }
        assert observation["checked_data"]
