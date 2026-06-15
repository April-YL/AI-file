from pathlib import Path
from types import SimpleNamespace

import openpyxl

from ingest.addition_test_sheet import (
    AdditionSampleOutputDataset,
    AdditionSampleRow,
    AdditionTestSheetDataset,
    AdditionTestedSampleRow,
)
from rules.delivery_completion import (
    DeliveryCompletionContext,
    check_delivery_completion,
)
from rules.models import Severity


def _ctx_with_addition_samples(*, completed: int, total: int):
    selected = [
        AdditionSampleRow(
            source_row=10 + idx,
            asset_id=f"FA-TEST-{idx:03d}",
            asset_name=f"资产{idx}",
            original_value=str(idx * 100),
        )
        for idx in range(1, total + 1)
    ]
    tested = [
        AdditionTestedSampleRow(
            source_row=30 + idx,
            asset_id=f"FA-TEST-{idx:03d}",
            asset_name=f"资产{idx}",
            original_value=str(idx * 100),
            evidence_description="合同/发票已检查",
        )
        for idx in range(1, completed + 1)
    ]
    return SimpleNamespace(
        addition_sample_output=AdditionSampleOutputDataset(
            source_file="dummy.xlsx",
            source_sheet="K.02.1a 新增选样输出",
            selected_samples=selected,
        ),
        addition_test=AdditionTestSheetDataset(
            source_file="dummy.xlsx",
            source_sheet="K.02.1 新增测试",
            tested_samples=tested,
        ),
    )


def test_first_delivery_fails_when_samples_exist_but_no_evidence():
    issues = check_delivery_completion(
        DeliveryCompletionContext(stage="first"),
        workbook_context=_ctx_with_addition_samples(completed=0, total=2),
    )

    assert {i.rule_id for i in issues} == {"first_delivery_standard"}
    assert issues[0].severity == Severity.FAIL
    assert issues[0].field == "tod_cutoff_evidence"


def test_final_delivery_uses_dl002_and_fails_over_50_percent():
    issues = check_delivery_completion(
        DeliveryCompletionContext(stage="final"),
        workbook_context=_ctx_with_addition_samples(completed=4, total=10),
    )

    sample_issues = [i for i in issues if i.field == "supporting_evidence_samples"]
    assert {i.rule_id for i in issues} == {"final_delivery_standard"}
    assert sample_issues[0].severity == Severity.FAIL
    assert "6/10" in sample_issues[0].message


def test_final_delivery_passes_samples_when_threshold_met():
    issues = check_delivery_completion(
        DeliveryCompletionContext(stage="final"),
        workbook_context=_ctx_with_addition_samples(completed=5, total=10),
    )

    assert [i for i in issues if i.field == "supporting_evidence_samples"] == []


def test_final_delivery_fails_when_workbook_has_unresolved_comment(tmp_path: Path):
    path = tmp_path / "comments.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.02.1 新增测试"
    ws["A1"] = "未解决 review note"
    wb.save(path)
    wb.close()

    issues = check_delivery_completion(
        DeliveryCompletionContext(stage="final"),
        workbook_context=_ctx_with_addition_samples(completed=1, total=1),
        workbook_path=path,
    )

    comment_issues = [i for i in issues if i.field == "comments_cleared"]
    assert len(comment_issues) == 1
    assert comment_issues[0].severity == Severity.FAIL
