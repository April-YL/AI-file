from decimal import Decimal

from ingest.models import AssetRecord, FieldMapping
from ingest.lead_sheet import CraAssertionRow, LeadBasicInfoField, LeadSheetDataset
from ingest.disposal_test_sheet import (
    DisposalAmountItem,
    DisposalExecutionPathDataset,
    DisposalParameterItem,
    DisposalSampleOutputDataset,
    DisposalSampleRow,
    DisposalTestSheetDataset,
    DisposalTestedSampleRow,
)
from ingest.records import DisposalListSummary, DisposalMethodBucket, FaListDataset
from ingest.rollforward_sheet import MovementTransactionAmount, RollforwardSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.disposal_list_rules import (
    check_disposal_list_net_values,
    check_disposal_method_classification,
    check_disposal_required_fields,
    check_disposal_other_reduction_over_tt,
)
from rules.models import Severity
from rules.disposal_runner import run_disposal_rules
from rules.lead_common import lead_thresholds, lead_tt
from tests.rules.test_disposal_reconciliation import _matrix


def _dataset(record: AssetRecord, fields: tuple[str, ...]) -> FaListDataset:
    return FaListDataset(
        source_file="test.xlsx",
        source_sheet="处置清单",
        mapped_fields=[FieldMapping(field, field, idx + 1) for idx, field in enumerate(fields)],
        records=[record],
    )


def test_required_fields_allows_missing_net_value_column():
    fields = (
        "asset_category",
        "asset_id",
        "asset_name",
        "original_value",
        "accumulated_depreciation",
        "impairment_provision",
        "disposal_date",
        "disposal_method",
    )
    dataset = _dataset(
        AssetRecord(
            source_row=2,
            asset_category="设备",
            asset_id="FA-D-001",
            asset_name="设备A",
            original_value="1000",
            accumulated_depreciation="700",
            impairment_provision="0",
            disposal_date="2025-01-01",
            disposal_method="出售",
        ),
        fields,
    )
    assert check_disposal_required_fields(dataset) == []


def test_required_fields_requires_impairment_column():
    dataset = _dataset(
        AssetRecord(source_row=2, asset_id="FA-D-001"),
        ("asset_id", "asset_name", "original_value", "accumulated_depreciation", "disposal_date", "disposal_method"),
    )
    issues = check_disposal_required_fields(dataset)
    assert any(issue.field == "impairment_provision" and issue.severity == Severity.FAIL for issue in issues)


def test_net_value_recalculation_accepts_negative_accumulated_depreciation_and_flags_error():
    fields = ("asset_id", "original_value", "accumulated_depreciation", "impairment_provision", "net_value")
    good = _dataset(
        AssetRecord(
            source_row=2,
            asset_id="FA-D-001",
            original_value="1000",
            accumulated_depreciation="-700",
            impairment_provision="0",
            net_value="300",
        ),
        fields,
    )
    assert check_disposal_list_net_values(good) == []
    good.records[0].net_value = "350"
    issues = check_disposal_list_net_values(good)
    assert len(issues) == 1
    assert issues[0].severity == Severity.FAIL


def test_unclassified_and_other_reductions_are_review_items():
    summary = DisposalListSummary(
        source_file="test.xlsx",
        source_sheet="处置清单",
        record_count=2,
        other_reduction_net_value="500",
        unclassified_net_value="100",
        buckets=[
            DisposalMethodBucket(
                bucket_key="unknown",
                bucket_label="未识别",
                record_count=1,
                net_value_total="100",
                source_rows=[8],
            )
        ],
    )
    method_issues = check_disposal_method_classification(summary)
    other_issues = check_disposal_other_reduction_over_tt(summary, None)
    assert method_issues[0].severity == Severity.NEED_REVIEW
    assert method_issues[0].source_row == 8
    assert other_issues[0].severity == Severity.NEED_REVIEW


def test_lead_tt_uses_cra_rows_when_basic_info_has_no_tt():
    lead = LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        cra_rows=[
            CraAssertionRow(assertion="存在", tt="300"),
            CraAssertionRow(assertion="计价", tt="200"),
        ],
    )

    thresholds = lead_thresholds(lead)

    assert lead_tt(lead) == thresholds.tt == 200
    assert thresholds.tt_source == "lead_cra_rows"


def test_other_reduction_uses_lead_cra_tt():
    summary = DisposalListSummary(
        source_file="test.xlsx",
        source_sheet="处置清单",
        record_count=1,
        other_reduction_net_value="150",
    )
    lead = LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        cra_rows=[
            CraAssertionRow(assertion="存在", tt="200"),
            CraAssertionRow(assertion="计价", tt="300"),
        ],
    )

    assert check_disposal_other_reduction_over_tt(summary, lead) == []


def test_other_reduction_warns_when_over_lead_cra_tt():
    summary = DisposalListSummary(
        source_file="test.xlsx",
        source_sheet="处置清单",
        record_count=1,
        other_reduction_net_value="250",
    )
    lead = LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        cra_rows=[
            CraAssertionRow(assertion="存在", tt="200"),
            CraAssertionRow(assertion="计价", tt="300"),
        ],
    )

    issues = check_disposal_other_reduction_over_tt(summary, lead)

    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW


def test_summary_waived_does_not_run_disposal_list_rules():
    dataset = _dataset(
        AssetRecord(source_row=2, asset_id="FA-D-001"),
        ("asset_id",),
    )
    issues = run_disposal_rules(
        disposal_list=dataset,
        disposal_list_summary=None,
        disposal_execution_path=DisposalExecutionPathDataset(
            path_kind="summary_waived",
            recognition_confidence=0.8,
        ),
    )
    assert issues == []


def test_disposal_runner_records_evidence_how_for_low_risk_k022_rules():
    fields = (
        "asset_category",
        "asset_id",
        "asset_name",
        "original_value",
        "accumulated_depreciation",
        "impairment_provision",
        "disposal_date",
        "disposal_method",
        "net_value",
    )
    disposal_list = _dataset(
        AssetRecord(
            source_row=2,
            asset_category="设备",
            asset_id="FA-D-001",
            asset_name="设备A",
            original_value="1000",
            accumulated_depreciation="700",
            impairment_provision="0",
            net_value="300",
            disposal_date="2025-01-01",
            disposal_method="出售",
        ),
        fields,
    )
    disposal_test = DisposalTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.2 处置测试",
        reconciliation_matrix=_matrix(),
        tested_samples=[
            DisposalTestedSampleRow(
                source_row=34,
                sample_type="代表性样本",
                asset_id="FA-D-001",
                asset_name="设备A",
                original_value="1000",
                accumulated_depreciation="700",
                impairment_provision="0",
                net_value="300",
                sale_price="300",
                disposal_gain_loss="0",
                support_sale_price="300",
                sale_price_difference="0",
                disposal_method="出售",
                evidence_description="合同与收款单一致",
                attribute_results=["Y", "Y", "Y"],
            )
        ],
        usable_for_rules=True,
    )
    sample_output = DisposalSampleOutputDataset(
        source_file="case.xlsx",
        source_sheet="K.02.2a 处置选样输出",
        amounts={"sample_pool_amount": DisposalAmountItem("样本池总体金额", "300", 41, 6)},
        parameters={
            "te": DisposalParameterItem("TE", "100", 15, 6),
            "covered_assertions": DisposalParameterItem("测试覆盖认定", "存在/发生", 16, 6),
            "cra": DisposalParameterItem("综合风险评估", "最低", 18, 6),
        },
        selected_samples=[
            DisposalSampleRow(
                source_row=30,
                sample_type="代表性样本",
                asset_id="FA-D-001",
                asset_name="设备A",
                net_value="300",
            )
        ],
        usable_for_rules=True,
    )
    execution_path = DisposalExecutionPathDataset(
        path_kind="executed",
        recognition_confidence=0.95,
        disposal_list_sheet="处置清单",
        disposal_test_sheet="K.02.2 处置测试",
        disposal_sample_output_sheet="K.02.2a 处置选样输出",
    )
    rollforward = RollforwardSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        movement_transactions=[
            MovementTransactionAmount(
                transaction_key="disposal",
                transaction_label="处置",
                measure="original_value",
                amount=Decimal("1000"),
                source_row=12,
            ),
            MovementTransactionAmount(
                transaction_key="disposal",
                transaction_label="处置",
                measure="accumulated_depreciation",
                amount=Decimal("700"),
                source_row=12,
            ),
            MovementTransactionAmount(
                transaction_key="disposal",
                transaction_label="处置",
                measure="impairment_provision",
                amount=Decimal("0"),
                source_row=12,
            ),
        ],
    )
    recorder = RuleExecutionRecorder()

    run_disposal_rules(
        disposal_test=disposal_test,
        disposal_sample_output=sample_output,
        disposal_execution_path=execution_path,
        disposal_list=disposal_list,
        disposal_list_summary=DisposalListSummary(
            source_file="case.xlsx",
            source_sheet="处置清单",
            record_count=1,
            sale_scrap_net_value="300",
        ),
        rollforward=rollforward,
        lead=LeadSheetDataset(
            source_file="case.xlsx",
            source_sheet="K.00 Lead Sheet",
            basic_info_fields=[
                LeadBasicInfoField(field_key="te", label="TE", value="100", source_row=8, source_col=4),
                LeadBasicInfoField(field_key="sad", label="SAD", value="5", source_row=9, source_col=4),
            ],
            cra_rows=[CraAssertionRow(assertion="存在/发生", cra="Minimal", tt="200", source_row=16)],
        ),
        recorder=recorder,
    )

    items = {item["rule_id"]: item for item in recorder.to_ledger()["items"]}
    for rule_id in (
        "disposal_reconciliation_readability",
        "disposal_reconciliation_formula_source",
        "disposal_net_value_recalculation",
        "disposal_rollforward_reconciliation",
        "disposal_required_fields",
        "disposal_list_net_value_recalculation",
        "disposal_sample_pool_amount_match",
        "disposal_sample_match",
        "disposal_difference_investigation",
        "disposal_method_classification",
        "disposal_other_reduction_over_tt",
        "disposal_sampling_te_cra_consistency",
        "disposal_sample_replacement_reason",
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
