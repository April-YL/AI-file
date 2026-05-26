from unittest.mock import patch

from openpyxl import Workbook

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from llm.config import LlmConfig
from llm.summary_psp_review import build_sheet_semantic_issues, review_waiver_reason_with_llm


def _config() -> LlmConfig:
    return LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
    )


def test_review_waiver_reason_with_llm_parses_result():
    row = PspProgramRow(
        procedure_name="K.03.2 折旧测试TOD",
        sheet_ref="K.03.2 折旧测试TOD",
        execution_status="否",
        waiver_reason="本期金额不大。",
        notes=None,
        source_row=19,
        is_psp=False,
    )
    with patch(
        "llm.summary_psp_review.chat_completion_json",
        return_value={
            "adequacy": "insufficient",
            "rationale": "仅有金额描述，未说明风险应对",
            "suggested_action": "补充替代程序与证据来源",
        },
    ):
        res = review_waiver_reason_with_llm(row, _config())
    assert res is not None
    assert res.adequacy == "insufficient"


def test_build_sheet_semantic_issues_for_weak_match(tmp_path):
    wb_path = tmp_path / "wb.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "K.02 新增"
    ws["A1"] = "新增资产清单"
    ws["A2"] = "资产名称"
    wb.save(wb_path)

    ds = SummarySheetDataset(
        source_file=str(wb_path),
        source_sheet="汇总",
        header_row=1,
        programs=[
            PspProgramRow(
                procedure_name="K.02.1 新增测试",
                sheet_ref="K.02.1 细节测试",
                execution_status="是",
                waiver_reason=None,
                notes=None,
                source_row=10,
                is_psp=False,
            )
        ],
    )

    with patch(
        "llm.summary_psp_review.chat_completion_json",
        return_value={
            "assessment": "match_supported",
            "chosen_sheet": "K.02 新增",
            "rationale": "候选页出现新增资产测试字段",
            "suggested_action": "确认并更新汇总页程序页引用",
        },
    ):
        issues = build_sheet_semantic_issues(
            ds,
            _config(),
            workbook_path=str(wb_path),
            workbook_sheet_titles=["K.02 新增"],
        )

    assert len(issues) == 1
    assert "更可能对应" in issues[0].message
