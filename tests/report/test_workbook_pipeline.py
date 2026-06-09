from pathlib import Path

import openpyxl
import pytest

from ingest.addition_test_sheet import AdditionExecutionPathDataset, AdditionTestSheetDataset
from ingest.workbook_context import WorkbookQcContext
from report.pipeline import run_workbook_qc, run_workbook_qc_from_path
from rules.delivery_completion import DeliveryCompletionContext
from rules.models import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CASE_B = (
    Path(__file__).resolve().parents[2]
    / "固定资产质检agent"
    / "案例库"
    / "K1 SWP 固定资产 20251231 B医疗公司.xlsx"
)


@pytest.fixture
def workbook_demo(tmp_path: Path) -> Path:
    path = tmp_path / "workbook_demo.xlsx"
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "汇总"
    ws_sum.append(["程序", "工作表", "是否执行", "不执行原因"])
    ws_sum.append(["K.01 后推", "K.01", "是", ""])
    ws_sum.append(["PSP-折旧测试", "K.03.1", "否", ""])
    ws_sum.append(["PSP-新增", "K.02.1", "否", "已提供合同约定的购置清单"])
    ws_fa = wb.create_sheet("FA list")
    with (FIXTURES / "fa_list_mixed.csv").open(encoding="utf-8-sig") as f:
        for line in f:
            ws_fa.append(line.strip().split(","))
    wb.save(path)
    wb.close()
    return path


def test_workbook_qc_includes_psp_and_fa_list(workbook_demo: Path):
    report = run_workbook_qc_from_path(str(workbook_demo), llm=False)
    rule_ids = {i.rule_id for i in report.issues}
    assert "psp_completion" in rule_ids or any(
        i.dict_rule_code == "AE-003" for i in report.issues
    )
    assert "fa_list_required_fields" in rule_ids
    assert report.procedure_code == "WORKBOOK"
    severities = {i.severity for i in report.issues}
    assert Severity.FAIL in severities


def test_workbook_qc_delivery_stage_selects_first_rule(workbook_demo: Path):
    report = run_workbook_qc_from_path(
        str(workbook_demo),
        llm=False,
        delivery_context=DeliveryCompletionContext(stage="first"),
    )

    delivery_issues = [
        i for i in report.issues if i.rule_id in {"first_delivery_standard", "final_delivery_standard"}
    ]
    assert {i.rule_id for i in delivery_issues} == {"first_delivery_standard"}
    assert "first_delivery_standard" in report.rule_ids
    assert "final_delivery_standard" not in report.rule_ids


def test_workbook_qc_delivery_stage_selects_final_rule(workbook_demo: Path):
    report = run_workbook_qc_from_path(
        str(workbook_demo),
        llm=False,
        delivery_context=DeliveryCompletionContext(stage="final"),
    )

    delivery_issues = [
        i for i in report.issues if i.rule_id in {"first_delivery_standard", "final_delivery_standard"}
    ]
    assert {i.rule_id for i in delivery_issues} == {"final_delivery_standard"}
    assert "final_delivery_standard" in report.rule_ids
    assert "first_delivery_standard" not in report.rule_ids


@pytest.mark.skipif(not CASE_B.exists(), reason="B company case workbook not available")
def test_workbook_qc_b_company_includes_addition_sheet_section():
    report = run_workbook_qc_from_path(str(CASE_B), llm=False)
    data = report.to_dict()
    section = data["addition_sheet_section"]
    preview = section["consistency_preview"]

    assert section["addition_test"]["source_sheet"] == "K.02.1 新增测试 "
    assert section["addition_sample_output"]["source_sheet"] == "K.02.1a 新增选样输出"
    assert section["addition_sample_output"]["parameters"]["te"]["value"] == "241,890.00"
    assert section["addition_sample_output"]["parameters"]["cra"]["value"] == "最低"
    assert preview["selected_count"] == 1
    assert preview["tested_count"] == 1
    assert preview["matched_count"] == 1
    assert preview["key_item_selected_amount"] == "380000"
    assert preview["key_item_tested_amount"] == "380000"
    assert "addition_sample_match" in report.rule_ids
    assert not [issue for issue in report.issues if issue.rule_id == "addition_sample_match"]


def test_workbook_qc_includes_addition_llm_issue(monkeypatch):
    monkeypatch.setenv("FA_QC_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("FA_QC_LLM_ENABLED", "true")

    from rules.models import QcIssue

    ctx = WorkbookQcContext(
        source_file="addition_llm_demo.xlsx",
        fa_list=None,
        summary=None,
        lead=None,
        rollforward=None,
        addition_list=None,
        addition_test=AdditionTestSheetDataset(
            source_file="addition_llm_demo.xlsx",
            source_sheet="K.02.1 新增测试",
            waiver_note_text="No narrative support provided.",
            waiver_note_rows=[12],
        ),
        addition_sample_output=None,
        addition_execution_path=AdditionExecutionPathDataset(
            path_kind="test_sheet_waiver_note",
            recognition_confidence=0.9,
            summary_status="waived",
            summary_waiver_reason="below SAD",
            summary_source_row=8,
            addition_test_sheet="K.02.1 新增测试",
            test_sheet_waiver_note="No narrative support provided.",
            test_sheet_waiver_rows=[12],
        ),
        disposal_list=None,
        structure=None,
        reconciliations=[],
    )

    mock_issue = QcIssue(
        asset_id=None,
        rule_id="addition_semantic_review",
        field="waiver_reason",
        severity=Severity.WARN,
        message="mock addition semantic issue",
        suggestion="document waiver rationale",
        procedure_code="K.02.1",
        source_sheet="K.02.1 新增测试",
        source_row=12,
    )

    monkeypatch.setattr("llm.addition_review.build_addition_llm_issues", lambda *args, **kwargs: [mock_issue])
    monkeypatch.setattr(
        "report.pipeline.enrich_report_with_llm",
        lambda report, config, summary=None, workbook=None: report,
    )
    report = run_workbook_qc(ctx, llm=True)

    assert any(i.rule_id == "addition_semantic_review" for i in report.issues)
    assert "addition_semantic" in {d["key"] for d in report.runtime_timings["llm_details"]}
