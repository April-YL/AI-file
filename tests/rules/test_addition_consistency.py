from pathlib import Path

import pytest

from ingest.addition_test_sheet import (
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
