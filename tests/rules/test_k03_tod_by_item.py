from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl

from ingest.k03_sheet import load_k03_sheets_from_workbook
from ingest.lead_sheet import LeadBasicInfoField, LeadSheetDataset, MaterialityCapture
from ingest.rollforward_sheet import MovementTransactionAmount, RollforwardSheetDataset
from ingest.workbook_context import WorkbookQcContext
from llm.workbook_payload import build_workbook_llm_payload
from report.pipeline import run_workbook_qc
from rules.k03_tod_by_item import run_k03_tod_by_item_rules
from rules.models import Severity


def _lead_with_sad(value: str | None = "5") -> LeadSheetDataset:
    fields = []
    materiality = []
    if value is not None:
        fields.append(
            LeadBasicInfoField(
                field_key="sad",
                label="名义金额 (SAD)",
                value=value,
                source_row=3,
                source_col=2,
            )
        )
        materiality.append(
            MaterialityCapture(
                field_key="sad",
                label="名义金额 (SAD)",
                workpaper_value=value,
                source_row=3,
                source_col_workpaper=2,
            )
        )
    return LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=fields,
        materiality=materiality,
    )


def _rf_with_depreciation(amount: str | None = "100") -> RollforwardSheetDataset:
    transactions = []
    if amount is not None:
        transactions.append(
            MovementTransactionAmount(
                transaction_key="depreciation",
                transaction_label="计提折旧",
                measure="accumulated_depreciation",
                amount=Decimal(amount),
                source_row=20,
            )
        )
    return RollforwardSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=2,
        mapped_fields=[],
        movement_transactions=transactions,
    )


def _save(wb: openpyxl.Workbook, path: Path) -> Path:
    wb.save(path)
    wb.close()
    return path


def _workbook(
    path: Path,
    *,
    rows: list[list],
    total: list | None = None,
    conclusion: str | None = "未见重大差异",
    headers: list[str] | None = None,
) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.03.2 折旧测试"
    ws.append(["说明", "TOD-by item 全量折旧测试"])
    ws.append([])
    ws.append(
        headers
        or [
            "资产编号",
            "资产名称",
            "原值",
            "残值率",
            "折旧年限",
            "本期折旧",
            "管理层计算折旧",
            "审计重新计算折旧",
            "差异",
            "备注",
        ]
    )
    for row in rows:
        ws.append(row)
    if total is not None:
        ws.append(total)
    if conclusion is not None:
        ws.append(["结论", conclusion])
    return _save(wb, path)


def _dataset(path: Path):
    return load_k03_sheets_from_workbook(path)[0]


def test_tod_by_item_normal_passes_without_findings(tmp_path: Path):
    path = _workbook(
        tmp_path / "normal.xlsx",
        rows=[["FA-TEST-001", "设备A", 1200, "5%", 60, 100, 100, 100, 0, ""]],
        total=["合计", "", 1200, "", "", 100, 100, 100, 0, ""],
    )

    issues = run_k03_tod_by_item_rules(
        _dataset(path),
        lead=_lead_with_sad("5"),
        rollforward=_rf_with_depreciation("100"),
    )

    assert issues == []


def test_tod_by_item_asset_difference_over_sad_without_explanation_fails(tmp_path: Path):
    path = _workbook(
        tmp_path / "asset_diff.xlsx",
        rows=[["FA-TEST-001", "设备A", 1200, "5%", 60, 112, 112, 100, 12, ""]],
        total=["合计", "", 1200, "", "", 112, 112, 100, 12, ""],
        conclusion=None,
    )

    issues = run_k03_tod_by_item_rules(
        _dataset(path),
        lead=_lead_with_sad("5"),
        rollforward=_rf_with_depreciation("112"),
    )

    assert any(
        i.rule_id == "k03_tod_by_item_difference_over_sad"
        and i.severity == Severity.FAIL
        and i.source_row == 4
        for i in issues
    )


def test_tod_by_item_difference_column_formula_error_fails_with_tolerance(tmp_path: Path):
    path = _workbook(
        tmp_path / "bad_diff_col.xlsx",
        rows=[["FA-TEST-001", "设备A", 1200, "5%", 60, 100, 100, 98, 1, "分类差异已说明"]],
        total=["合计", "", 1200, "", "", 100, 100, 98, 2, ""],
    )

    issues = run_k03_tod_by_item_rules(
        _dataset(path),
        lead=_lead_with_sad("5"),
        rollforward=_rf_with_depreciation("100"),
    )

    assert any(
        i.rule_id == "k03_tod_by_item_difference_column"
        and i.severity == Severity.FAIL
        for i in issues
    )


def test_tod_by_item_total_difference_over_sad_without_explanation_fails(tmp_path: Path):
    path = _workbook(
        tmp_path / "total_diff.xlsx",
        rows=[
            ["FA-TEST-001", "设备A", 1200, "5%", 60, 100, 100, 98, 2, "尾差"],
            ["FA-TEST-002", "设备B", 1200, "5%", 60, 100, 100, 98, 2, "尾差"],
        ],
        total=["合计", "", 2400, "", "", 200, 220, 200, 20, ""],
        conclusion=None,
    )

    issues = run_k03_tod_by_item_rules(
        _dataset(path),
        lead=_lead_with_sad("5"),
        rollforward=_rf_with_depreciation("200"),
    )

    assert any(
        i.rule_id == "k03_tod_by_item_total_difference_over_sad"
        and i.severity == Severity.FAIL
        for i in issues
    )


def test_tod_by_item_difference_needs_review_without_sad(tmp_path: Path):
    path = _workbook(
        tmp_path / "no_sad.xlsx",
        rows=[["FA-TEST-001", "设备A", 1200, "5%", 60, 112, 112, 100, 12, ""]],
        total=["合计", "", 1200, "", "", 112, 112, 100, 12, ""],
        conclusion=None,
    )

    issues = run_k03_tod_by_item_rules(
        _dataset(path),
        lead=_lead_with_sad(None),
        rollforward=_rf_with_depreciation("112"),
    )

    assert any(
        i.rule_id == "k03_tod_by_item_sad_unavailable"
        and i.severity == Severity.NEED_REVIEW
        for i in issues
    )
    assert not any(
        i.rule_id == "k03_tod_by_item_difference_over_sad"
        and i.severity == Severity.FAIL
        for i in issues
    )


def test_tod_by_item_noncritical_field_missing_does_not_fail(tmp_path: Path):
    headers = [
        "资产编号",
        "资产名称",
        "管理层计算折旧",
        "审计重新计算折旧",
        "差异",
        "备注",
    ]
    path = _workbook(
        tmp_path / "missing_noncritical.xlsx",
        headers=headers,
        rows=[["FA-TEST-001", "设备A", 100, 100, 0, ""]],
        total=["合计", "", 100, 100, 0, ""],
    )

    issues = run_k03_tod_by_item_rules(
        _dataset(path),
        lead=_lead_with_sad("5"),
        rollforward=_rf_with_depreciation("100"),
    )

    assert not any(i.severity == Severity.FAIL for i in issues)


def test_tod_by_item_rollforward_depreciation_over_sad_without_explanation_fails(tmp_path: Path):
    path = _workbook(
        tmp_path / "rf_diff.xlsx",
        rows=[["FA-TEST-001", "设备A", 1200, "5%", 60, 112, 112, 112, 0, ""]],
        total=["合计", "", 1200, "", "", 112, 112, 112, 0, ""],
        conclusion=None,
    )

    issues = run_k03_tod_by_item_rules(
        _dataset(path),
        lead=_lead_with_sad("5"),
        rollforward=_rf_with_depreciation("100"),
    )

    assert any(
        i.rule_id == "k03_tod_by_item_rollforward_depreciation"
        and i.severity == Severity.FAIL
        for i in issues
    )


def test_pipeline_runs_k03_rules_without_expanding_context(tmp_path: Path):
    path = _workbook(
        tmp_path / "pipeline.xlsx",
        rows=[["FA-TEST-001", "设备A", 1200, "5%", 60, 112, 112, 100, 12, ""]],
        total=["合计", "", 1200, "", "", 112, 112, 100, 12, ""],
        conclusion=None,
    )
    k03_sheets = load_k03_sheets_from_workbook(path)
    ctx = WorkbookQcContext(
        source_file=str(path),
        fa_list=None,
        summary=None,
        lead=_lead_with_sad("5"),
        rollforward=_rf_with_depreciation("112"),
        k03_sheets=k03_sheets,
    )

    report = run_workbook_qc(ctx, llm=False)

    assert any(i.rule_id == "k03_tod_by_item_difference_over_sad" for i in report.issues)
    data = k03_sheets[0].to_dict()
    assert "detail_rows" not in data
    payload = build_workbook_llm_payload(ctx)
    assert "k03_sheets" not in payload
