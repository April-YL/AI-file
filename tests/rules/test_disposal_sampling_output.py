from ingest.disposal_test_sheet import (
    DisposalParameterItem,
    DisposalSampleOutputDataset,
    DisposalTestedSampleRow,
    DisposalTestSheetDataset,
)
from ingest.records import DisposalListSummary
from rules.disposal_sampling_output import (
    check_disposal_sample_pool_amount,
    check_disposal_sample_replacement_reason,
)
from rules.models import Severity


def test_disposal_sample_pool_matches_sale_scrap_not_total_reductions():
    summary = DisposalListSummary(
        source_file="test.xlsx",
        source_sheet="处置清单",
        record_count=2,
        total_net_value="800",
        sale_scrap_net_value="300",
        other_reduction_net_value="500",
    )
    output = DisposalSampleOutputDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2a",
        amounts={"sample_pool_amount": type("Item", (), {"amount": "300", "source_row": 8})()},
        usable_for_rules=True,
    )
    assert check_disposal_sample_pool_amount(summary, output) == []
    output.amounts["sample_pool_amount"].amount = "800"
    issues = check_disposal_sample_pool_amount(summary, output)
    assert issues[0].severity == Severity.FAIL


def test_disposal_replacement_sample_requires_reason():
    test = DisposalTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2",
        tested_samples=[
            DisposalTestedSampleRow(
                source_row=20,
                sample_type="替换样本",
                asset_id="FA-D-1",
                evidence_description="合同及发票",
            )
        ],
    )
    issues = check_disposal_sample_replacement_reason(test)
    assert issues[0].severity == Severity.NEED_REVIEW
