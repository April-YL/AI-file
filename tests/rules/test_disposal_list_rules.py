from ingest.models import AssetRecord, FieldMapping
from ingest.lead_sheet import CraAssertionRow, LeadSheetDataset
from ingest.disposal_test_sheet import DisposalExecutionPathDataset
from ingest.records import DisposalListSummary, DisposalMethodBucket, FaListDataset
from rules.disposal_list_rules import (
    check_disposal_list_net_values,
    check_disposal_method_classification,
    check_disposal_required_fields,
    check_disposal_other_reduction_over_tt,
)
from rules.models import Severity
from rules.disposal_runner import run_disposal_rules
from rules.lead_common import lead_thresholds, lead_tt


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
