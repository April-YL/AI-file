from openpyxl import Workbook

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.models import Severity
from rules.psp_completion import check_psp_completion


def _dataset(programs: list[PspProgramRow]) -> SummarySheetDataset:
    return SummarySheetDataset(
        source_file="test.xlsx",
        source_sheet="汇总",
        header_row=1,
        programs=programs,
    )


def test_waiver_missing_is_fail():
    rows = [
        PspProgramRow(
            procedure_name="PSP-折旧测试",
            sheet_ref="K.03.1",
            execution_status="否",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(_dataset(rows))
    assert any(i.severity == Severity.FAIL for i in issues)
    assert any(i.field == "waiver_reason" for i in issues)


def test_waiver_present_ok():
    rows = [
        PspProgramRow(
            procedure_name="PSP-新增",
            sheet_ref="K.02.1",
            execution_status="不适用",
            waiver_reason="客户已提供外部专家报告，范围已覆盖",
            notes=None,
            source_row=3,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(_dataset(rows))
    assert not any(i.severity == Severity.FAIL for i in issues)


def test_empty_execution_need_review():
    rows = [
        PspProgramRow(
            procedure_name="K.01 后推",
            sheet_ref="K.01",
            execution_status="",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=False,
        ),
    ]
    issues = check_psp_completion(_dataset(rows))
    assert any(i.severity == Severity.NEED_REVIEW for i in issues)


def test_no_programs_sheet_level_need_review():
    issues = check_psp_completion(
        SummarySheetDataset("t.xlsx", "", None, []),
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW


def test_yes_without_workbook_skips_sheet_cross_check():
    rows = [
        PspProgramRow(
            procedure_name="K.01 后推",
            sheet_ref="K.01",
            execution_status="是",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(_dataset(rows))
    assert not issues


def test_yes_matching_sheet_ok():
    rows = [
        PspProgramRow(
            procedure_name="K.01 后推",
            sheet_ref="K.01",
            execution_status="是",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(
        _dataset(rows),
        workbook_sheet_titles=["Lead", "K.01 后推-2024"],
    )
    assert not issues


def test_yes_missing_sheet_fail():
    rows = [
        PspProgramRow(
            procedure_name="测试",
            sheet_ref="K.99.9",
            execution_status="是",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(
        _dataset(rows),
        workbook_sheet_titles=["K.01"],
    )
    assert any(i.severity == Severity.FAIL for i in issues)


def test_yes_fuzzy_match_need_review():
    rows = [
        PspProgramRow(
            procedure_name="细节",
            sheet_ref="K.02.1 细节测试",
            execution_status="是",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(
        _dataset(rows),
        workbook_sheet_titles=["K.02 新增"],
    )
    assert any(i.severity == Severity.NEED_REVIEW for i in issues)
    assert not any(i.severity == Severity.FAIL for i in issues)


def test_yes_sheet_ref_fallback_from_procedure_name():
    rows = [
        PspProgramRow(
            procedure_name="执行 K.01 后推程序",
            sheet_ref="",
            execution_status="是",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(
        _dataset(rows),
        workbook_sheet_titles=["K.01 底稿"],
    )
    assert not issues


def test_yes_no_ref_need_review():
    rows = [
        PspProgramRow(
            procedure_name="仅名称无编号",
            sheet_ref="",
            execution_status="是",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(
        _dataset(rows),
        workbook_sheet_titles=["某页"],
    )
    assert any(i.field == "sheet_ref" and i.severity == Severity.NEED_REVIEW for i in issues)


def test_yes_sparse_sheet_warns(tmp_path):
    wb_path = tmp_path / "psp_sparse.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "K.01 后推"
    ws["A1"] = "hdr"
    wb.save(wb_path)

    rows = [
        PspProgramRow(
            procedure_name="K.01",
            sheet_ref="K.01",
            execution_status="是",
            waiver_reason=None,
            notes=None,
            source_row=2,
            is_psp=True,
        ),
    ]
    issues = check_psp_completion(
        _dataset(rows),
        workbook_sheet_titles=["K.01 后推"],
        workbook_path=str(wb_path),
    )
    assert any(i.field == "sheet_substance" and i.severity == Severity.WARN for i in issues)
