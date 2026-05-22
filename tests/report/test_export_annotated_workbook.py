from pathlib import Path

import openpyxl
import pytest

from report.export_annotated_workbook import (
    COMMENTS_SHEET_NAME,
    FA_LIST_COMMENTS_SHEET_NAME,
    build_comments_rows,
    build_fa_list_detail_rows,
    build_main_comments_rows,
    export_annotated_workbook,
    split_fa_list_issues,
)
from report.pipeline import run_workbook_qc_from_path
from rules.models import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_split_fa_list_issues():
    path = FIXTURES / "workbook_with_lead.xlsx"
    if not path.is_file():
        pytest.skip("fixture missing")
    report = run_workbook_qc_from_path(str(path), llm=False)
    issues = [i for i in report.issues if i.severity != Severity.PASS]
    fa, other = split_fa_list_issues(issues)
    assert all(i.procedure_code == "FA_LIST" for i in fa)
    assert all(i.procedure_code != "FA_LIST" for i in other)


def test_main_rows_fewer_than_fa_detail_when_many_fa_dupes():
    path = FIXTURES / "fa_list_mixed.xlsx"
    if not path.is_file():
        pytest.skip("fixture missing")
    from ingest.records import load_fa_list_from_workbook
    from rules.runner import run_fa_list_rules
    from rules.registry import attach_rule_metadata
    from rules.models import ColumnContext
    from report.summary import build_report

    ds = load_fa_list_from_workbook(path)
    ctx = ColumnContext(
        mapped_fields={m.standard_field for m in ds.mapped_fields},
        source_sheet=ds.source_sheet,
    )
    issues = attach_rule_metadata(run_fa_list_rules(ds.records, ctx))
    issues = [i for i in issues if i.severity != Severity.PASS]
    fa, other = split_fa_list_issues(issues)
    main_rows = build_main_comments_rows(other, fa)
    detail_rows = build_fa_list_detail_rows(fa)
    assert len(detail_rows) == len(fa)
    if len(fa) > 2:
        assert len(main_rows) < len(fa) + len(other)


def test_export_two_comment_sheets(tmp_path: Path):
    src = FIXTURES / "workbook_with_lead.xlsx"
    if not src.is_file():
        pytest.skip("fixture missing")
    report = run_workbook_qc_from_path(str(src), llm=False)
    out = tmp_path / "out.xlsx"
    export_annotated_workbook(report, src, out)
    wb = openpyxl.load_workbook(out, read_only=True)
    assert wb.sheetnames[0] == COMMENTS_SHEET_NAME
    assert wb.sheetnames[1] == FA_LIST_COMMENTS_SHEET_NAME
    assert wb[COMMENTS_SHEET_NAME].cell(1, 1).value == "EY Ref."
    wb.close()


def test_build_comments_rows_compat():
    path = FIXTURES / "workbook_with_lead.xlsx"
    if not path.is_file():
        pytest.skip("fixture missing")
    report = run_workbook_qc_from_path(str(path), llm=False)
    issues = [i for i in report.issues if i.severity != Severity.PASS]
    rows = build_comments_rows(issues)
    assert rows and rows[0][0] == 1
