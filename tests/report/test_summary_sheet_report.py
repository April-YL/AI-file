from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from report.summary_sheet_report import build_summary_sheet_section
from rules.models import QcIssue, Severity


def test_build_summary_sheet_section_includes_psp_and_programs():
    rows = [
        PspProgramRow("程序A", "K.01", "是", None, None, 2, True),
    ]
    ds = SummarySheetDataset(
        source_file="t.xlsx",
        source_sheet="汇总",
        header_row=5,
        programs=rows,
        layout="swp",
    )
    psp_issues = [
        QcIssue(
            asset_id=None,
            rule_id="psp_completion",
            field="sheet_ref",
            severity=Severity.WARN,
            message="x",
            suggestion="y",
            procedure_code="SUMMARY",
            source_sheet="汇总",
            source_row=2,
            dict_rule_code="AE-003",
        )
    ]
    sec = build_summary_sheet_section(ds, psp_issues)
    assert sec["ingested"] is True
    assert sec["program_count"] == 1
    assert sec["programs"][0]["sheet_ref"] == "K.01"
    assert sec["psp_completion"]["overall_severity"] == "WARN"
    assert sec["psp_completion"]["issue_count"] == 1
    assert len(sec["psp_completion"]["issues"]) == 1


def test_build_summary_sheet_section_pass_when_no_psp_issues():
    ds = SummarySheetDataset(
        "t.xlsx",
        "汇总",
        1,
        [PspProgramRow("n", "K.01", "是", None, None, 2, True)],
    )
    sec = build_summary_sheet_section(ds, [])
    assert sec["psp_completion"]["overall_severity"] == "PASS"
    assert sec["psp_completion"]["issue_count"] == 0
