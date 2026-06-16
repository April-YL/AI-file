from ingest.disposal_test_sheet import DisposalTestedSampleRow, DisposalTestSheetDataset
from rules.disposal_detailed_test import run_disposal_detailed_test_rules
from rules.models import Severity


def _test(sample: DisposalTestedSampleRow) -> DisposalTestSheetDataset:
    return DisposalTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2",
        tested_samples=[sample],
    )


def test_complete_sale_sample_passes_detailed_rules():
    sample = DisposalTestedSampleRow(
        source_row=10,
        asset_id="FA-D-1",
        original_value="1000",
        accumulated_depreciation="700",
        impairment_provision="0",
        net_value="300",
        sale_price="400",
        disposal_gain_loss="100",
        support_sale_price="400",
        sale_price_difference="0",
        evidence_description="合同、发票、收款证明",
        attribute_results=["Y", "Y", "Y"],
    )
    assert run_disposal_detailed_test_rules(_test(sample)) == []


def test_detailed_rules_flag_incomplete_attributes_and_bad_amounts():
    sample = DisposalTestedSampleRow(
        source_row=10,
        asset_id="FA-D-1",
        original_value="1000",
        accumulated_depreciation="700",
        impairment_provision="0",
        net_value="350",
        sale_price="400",
        disposal_gain_loss="10",
        support_sale_price="450",
        sale_price_difference="0",
        attribute_results=["Y"],
    )
    issues = run_disposal_detailed_test_rules(_test(sample))
    assert any(i.rule_id == "disposal_test_attributes_complete" and i.severity == Severity.FAIL for i in issues)
    assert any(i.rule_id == "disposal_test_amount_recalculation" and i.severity == Severity.FAIL for i in issues)
    assert any(i.rule_id == "disposal_sale_evidence_complete" and i.severity == Severity.FAIL for i in issues)


def test_reported_exception_requires_followup():
    sample = DisposalTestedSampleRow(
        source_row=10,
        asset_id="FA-D-1",
        attribute_results=["Y", "N", "Y"],
        evidence_description="合同及发票",
    )
    issues = run_disposal_detailed_test_rules(_test(sample))
    assert any(i.rule_id == "disposal_exception_followup" and i.severity == Severity.NEED_REVIEW for i in issues)
