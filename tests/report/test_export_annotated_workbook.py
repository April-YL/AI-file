from pathlib import Path

import openpyxl
import pytest

from report.export_annotated_workbook import (
    COMMENTS_SHEET_NAME,
    FA_LIST_COMMENTS_SHEET_NAME,
    LOCATOR_SHEET_NAME,
    build_comments_rows,
    build_fa_list_detail_rows,
    build_locator_rows,
    build_main_comments_rows,
    export_annotated_workbook,
    split_fa_list_issues,
)
from report.pipeline import run_workbook_qc_from_path
from rules.models import QcIssue, Severity

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
    assert wb.sheetnames[2] == LOCATOR_SHEET_NAME
    assert wb[COMMENTS_SHEET_NAME].cell(1, 1).value == "EY Ref."
    assert wb[LOCATOR_SHEET_NAME].cell(1, 1).value == "EY Ref."
    wb.close()


def test_answer_blank_agent_ref_in_last_column():
    issue = QcIssue(
        asset_id=None,
        rule_id="lead_required_fields",
        field="gaap",
        severity=Severity.FAIL,
        message="缺少适用会计准则",
        suggestion="在 Lead 表补充适用会计准则",
        procedure_code="K.00",
        source_sheet="K.00 Lead Sheet",
        source_row=7,
    )
    rows = build_main_comments_rows([issue], [])
    assert len(rows) == 1
    assert rows[0][4] is None
    assert "Agent 参考" not in (rows[0][3] or "")
    assert rows[0][6] == "在 Lead 表补充适用会计准则"


def test_build_comments_rows_compat():
    path = FIXTURES / "workbook_with_lead.xlsx"
    if not path.is_file():
        pytest.skip("fixture missing")
    report = run_workbook_qc_from_path(str(path), llm=False)
    issues = [i for i in report.issues if i.severity != Severity.PASS]
    rows = build_comments_rows(issues)
    assert rows and rows[0][0] == 1


def test_main_comment_rows_order_summary_then_lead_then_other():
    issues = [
        QcIssue(
            asset_id=None,
            rule_id="lead_required_fields",
            field="gaap",
            severity=Severity.FAIL,
            message="Lead 缺少会计准则",
            suggestion="补充",
            procedure_code="K.00",
            source_sheet="K.00 Lead Sheet",
            source_row=10,
        ),
        QcIssue(
            asset_id=None,
            rule_id="psp_completion",
            field="execution_status",
            severity=Severity.WARN,
            message="汇总页执行状态异常",
            suggestion="补充",
            procedure_code="SUMMARY",
            source_sheet="汇总",
            source_row=20,
        ),
        QcIssue(
            asset_id=None,
            rule_id="rollforward_exists",
            field=None,
            severity=Severity.NEED_REVIEW,
            message="后推页缺失",
            suggestion="补充",
            procedure_code="K.01",
            source_sheet="K.01 Agree SL to GL",
            source_row=5,
        ),
    ]
    rows = build_main_comments_rows(issues, [])
    tabs = [r[1] for r in rows]
    assert tabs == ["汇总", "K.00 Lead Sheet", "K.01 Agree SL to GL"]


def test_question_comment_is_compact():
    issue = QcIssue(
        asset_id=None,
        rule_id="psp_completion",
        field="waiver_reason",
        severity=Severity.WARN,
        message=(
            "程序「K.03.2 折旧测试TOD」不执行理由语义上不足；模型提示："
            "未说明业务风险、阈值判断与替代程序，建议补充详细说明并给出证据来源。"
        ),
        suggestion="补充说明",
        procedure_code="SUMMARY",
        source_sheet="汇总",
        source_row=18,
    )
    rows = build_main_comments_rows([issue], [])
    question = rows[0][3]
    assert question.startswith("[WARN] psp_completion ")
    assert "模型提示" not in question
    assert len(question) <= 90


def test_question_comment_uses_short_title_mapping():
    issue = QcIssue(
        asset_id=None,
        rule_id="psp_completion",
        field="execution_status_consistency",
        severity=Severity.NEED_REVIEW,
        message="很长的原始信息，不应直接出现在 Question/Comment 里。",
        suggestion="补充说明",
        procedure_code="SUMMARY",
        source_sheet="汇总",
        source_row=18,
        dict_rule_code="AE-003",
    )
    rows = build_main_comments_rows([issue], [])
    question = rows[0][3]
    assert question == "[NEED_REVIEW] AE-003 汇总勾选与底稿证据不一致（K.03.2/TOD）"


def test_locator_rows_include_navigate_ref():
    issue = QcIssue(
        asset_id=None,
        rule_id="lead_required_fields",
        field="gaap",
        severity=Severity.FAIL,
        message="缺少适用会计准则",
        suggestion="补充",
        procedure_code="K.00",
        source_sheet="K.00 Lead Sheet",
        source_row=7,
        dict_rule_code="LEAD-001",
    )
    rows = build_locator_rows([issue])
    assert len(rows) == 1
    assert rows[0][2] == "LEAD-001"
    assert rows[0][4] == "$B$7"
    assert rows[0][7] == "K.00 Lead Sheet!B7"
