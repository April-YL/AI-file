from pathlib import Path

import pytest

from ingest.addition_test_sheet import (
    AdditionSampleOutputDataset,
    AdditionSampleRow,
    AdditionTestSheetDataset,
    AdditionTestedSampleRow,
    ModuleAssessment,
    load_addition_sample_output_from_workbook,
    load_addition_test_from_workbook,
)
from rules.addition_consistency import (
    build_addition_consistency_preview,
    check_addition_sample_match,
)

CASE_B = (
    Path(__file__).resolve().parents[2]
    / "固定资产质检agent"
    / "案例库"
    / "K1 SWP 固定资产 20251231 B医疗公司.xlsx"
)


@pytest.mark.skipif(not CASE_B.exists(), reason="B company case workbook not available")
def test_b_company_addition_selected_sample_matches_tested_sample():
    addition_test = load_addition_test_from_workbook(
        CASE_B,
        sheet_name="K.02.1 新增测试 ",
        max_rows=120,
    )
    sample_output = load_addition_sample_output_from_workbook(
        CASE_B,
        sheet_name="K.02.1a 新增选样输出",
        max_rows=120,
    )

    preview = build_addition_consistency_preview(addition_test, sample_output)

    assert sample_output.parameters["te"].value == "241,890.00"
    assert sample_output.parameters["covered_assertions"].value == "存在/发生, 计量/计价, 权利与义务"
    assert sample_output.parameters["cra"].value == "最低"
    assert preview.selected_count == 1
    assert preview.tested_count == 1
    assert preview.matched_count == 1
    assert preview.unmatched_selected == []
    assert preview.unmatched_tested == []
    assert preview.key_item_selected_count == 1
    assert preview.key_item_tested_count == 1
    assert preview.key_item_selected_amount == "380000"
    assert preview.key_item_tested_amount == "380000"
    assert preview.sample_method == "随机抽样 (Random)"

    assert check_addition_sample_match(addition_test, sample_output) == []


def test_exception_summary_module_counts_as_note():
    addition_test = AdditionTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1 新增测试",
        tested_samples=[],
        module_assessments=[
            ModuleAssessment(
                module_key="exception_summary",
                module_name="异常说明与结论",
                status="recognized",
                confidence=0.9,
                evidence=["无异常情况"],
            )
        ],
    )
    sample_output = load_addition_sample_output_from_workbook(
        CASE_B,
        sheet_name="K.02.1a 新增选样输出",
        max_rows=120,
    )

    issues = check_addition_sample_match(addition_test, sample_output)

    assert not [issue for issue in issues if issue.field == "exception_summary"]


def test_exception_summary_recognition_is_not_a_finding():
    addition_test = AdditionTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1",
        tested_samples=[
            AdditionTestedSampleRow(
                source_row=20,
                asset_id="FA-TEST-001",
                asset_name="Asset",
                original_value="100",
                evidence_amount="90",
                amount_difference="10",
            )
        ],
    )
    sample_output = AdditionSampleOutputDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1a",
    )

    issues = check_addition_sample_match(addition_test, sample_output)

    assert not [issue for issue in issues if issue.field == "exception_summary"]


def test_unactivated_replacement_sample_is_not_required_in_detailed_test():
    addition_test = AdditionTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1",
        tested_samples=[
            AdditionTestedSampleRow(
                source_row=20,
                asset_id="FA-TEST-001",
                asset_name="Primary",
                original_value="100",
            )
        ],
    )
    sample_output = AdditionSampleOutputDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1a",
        selected_samples=[
            AdditionSampleRow(
                source_row=30,
                sample_type="代表性样本",
                asset_id="FA-TEST-001",
                asset_name="Primary",
                original_value="100",
            ),
            AdditionSampleRow(
                source_row=31,
                sample_type="替换样本",
                asset_id="FA-TEST-R01",
                asset_name="Reserve",
                original_value="80",
            ),
        ],
    )

    assert check_addition_sample_match(addition_test, sample_output) == []


def test_addition_sample_match_finding_uses_selected_sample_location():
    addition_test = AdditionTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1",
        tested_samples=[],
    )
    sample_output = AdditionSampleOutputDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1a",
        selected_samples=[
            AdditionSampleRow(
                source_row=30,
                sample_type="代表性样本",
                asset_id="FA-TEST-001",
                asset_name="Asset",
                original_value="100",
            )
        ],
    )

    issues = check_addition_sample_match(addition_test, sample_output)
    sample_match_issues = [issue for issue in issues if issue.field == "sample_match"]

    assert sample_match_issues
    assert all(issue.source_sheet == "K.02.1a" for issue in sample_match_issues)
    assert all(issue.source_row == 30 for issue in sample_match_issues)
