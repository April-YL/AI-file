from pathlib import Path

import openpyxl

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.addition_test_package import (
    check_addition_test_package,
    check_disposal_test_package,
)
from rules.models import Severity


def _summary(status: str = "是") -> SummarySheetDataset:
    return SummarySheetDataset(
        source_file="dummy.xlsx",
        source_sheet="汇总",
        header_row=1,
        programs=[
            PspProgramRow(
                procedure_name="K.02.1 新增测试",
                sheet_ref="K.02.1 新增测试",
                execution_status=status,
                waiver_reason=None,
                notes=None,
                source_row=12,
            ),
            PspProgramRow(
                procedure_name="K.02.1a 新增选样输出",
                sheet_ref="K.02.1a 新增选样输出",
                execution_status=None,
                waiver_reason=None,
                notes=None,
                source_row=13,
            ),
        ],
        layout="swp",
    )


def _summary_with_disposal(status: str = "是") -> SummarySheetDataset:
    return SummarySheetDataset(
        source_file="dummy.xlsx",
        source_sheet="汇总",
        header_row=1,
        programs=[
            PspProgramRow(
                procedure_name="K.02.2 处置测试",
                sheet_ref="K.02.2 处置测试",
                execution_status=status,
                waiver_reason=None,
                notes=None,
                source_row=20,
            ),
            PspProgramRow(
                procedure_name="K.02.2a 处置选样输出",
                sheet_ref="K.02.2a 处置选样输出",
                execution_status=None,
                waiver_reason=None,
                notes=None,
                source_row=21,
            ),
        ],
        layout="swp",
    )


def test_addition_package_complete_accepts_standard_names():
    issues = check_addition_test_package(
        _summary(),
        workbook_sheet_titles=[
            "汇总",
            "新增清单",
            "K.02.1 新增测试",
            "K.02.1a 新增选样输出",
        ],
    )
    assert issues == []


def test_addition_package_accepts_name_variants():
    issues = check_addition_test_package(
        _summary(),
        workbook_sheet_titles=[
            "汇总",
            "K.02.1b 新增清单",
            "K.02.1 细节测试",
            "新增抽样输出结果",
        ],
    )
    assert issues == []


def test_addition_package_reports_missing_sampling_output():
    issues = check_addition_test_package(
        _summary(),
        workbook_sheet_titles=[
            "汇总",
            "新增清单",
            "K.02.1 新增测试",
        ],
    )
    assert len(issues) == 1
    assert issues[0].rule_id == "addition_test_package_complete"
    assert issues[0].severity == Severity.NEED_REVIEW
    assert "抽样输出结果" in issues[0].message


def test_addition_package_reports_need_review_when_multiple_sheets_missing():
    issues = check_addition_test_package(
        _summary(),
        workbook_sheet_titles=[
            "汇总",
            "K.02.1 新增测试",
        ],
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].severity != Severity.FAIL
    assert "新增清单" in issues[0].message
    assert "抽样输出结果" in issues[0].message
    assert "不代表程序一定未执行" in issues[0].message


def test_addition_package_does_not_run_when_not_executed():
    issues = check_addition_test_package(
        _summary(status="否"),
        workbook_sheet_titles=[
            "汇总",
            "K.02.1 新增测试",
        ],
    )
    assert issues == []


def test_disposal_package_complete_accepts_standard_names():
    issues = check_disposal_test_package(
        _summary_with_disposal(),
        workbook_sheet_titles=[
            "汇总",
            "处置清单",
            "K.02.2 处置测试",
            "K.02.2a 处置选样输出",
        ],
    )
    assert issues == []


def test_disposal_package_accepts_name_variants():
    issues = check_disposal_test_package(
        _summary_with_disposal(),
        workbook_sheet_titles=[
            "汇总",
            "K.02.2b 减少清单",
            "K.02.2 细节测试",
            "处置抽样输出结果",
        ],
    )
    assert issues == []


def test_disposal_package_does_not_use_addition_sampling_output():
    issues = check_disposal_test_package(
        _summary_with_disposal(),
        workbook_sheet_titles=[
            "汇总",
            "处置清单",
            "K.02.2 处置测试",
            "K.02.1a 新增选样输出",
        ],
    )
    assert len(issues) == 1
    assert issues[0].rule_id == "disposal_test_package_complete"
    assert issues[0].severity == Severity.NEED_REVIEW
    assert "抽样输出结果" in issues[0].message


def test_disposal_package_does_not_run_when_not_executed():
    issues = check_disposal_test_package(
        _summary_with_disposal(status="否"),
        workbook_sheet_titles=[
            "汇总",
            "K.02.2 处置测试",
        ],
    )
    assert issues == []


def test_disposal_package_documented_limited_on_test_sheet(tmp_path: Path):
    path = tmp_path / "wb.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.02.2 处置测试"
    ws["A5"] = "本期处置资产净值小于TE，未执行抽样测试"
    wb.save(path)

    issues = check_disposal_test_package(
        _summary_with_disposal(status="是"),
        workbook_sheet_titles=[
            "汇总",
            "K.02.2 处置测试",
        ],
        workbook_path=path,
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert "不等于程序未执行" in issues[0].message
    assert "小于TE" in issues[0].message


def test_addition_package_uses_summary_notes_as_limited_execution():
    summary = SummarySheetDataset(
        source_file="dummy.xlsx",
        source_sheet="汇总",
        header_row=1,
        programs=[
            PspProgramRow(
                procedure_name="K.02.1 新增测试",
                sheet_ref="K.02.1 新增测试",
                execution_status="是",
                waiver_reason=None,
                notes="本期新增原值小于TE，未执行抽样",
                source_row=12,
            ),
        ],
        layout="swp",
    )
    issues = check_addition_test_package(
        summary,
        workbook_sheet_titles=["汇总", "K.02.1 新增测试"],
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert "不等于程序未执行" in issues[0].message
