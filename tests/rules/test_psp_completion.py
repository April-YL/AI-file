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
