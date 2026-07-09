from __future__ import annotations

from pathlib import Path

import openpyxl

from ingest.k03_sheet import (
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    load_k03_sheets_from_workbook,
)
from ingest.lead_sheet import LeadBasicInfoField, LeadSheetDataset, MaterialityCapture
from rules.k03_sap import run_k03_sap_rules
from rules.models import Severity


def _lead(cra: str = "Minimal", te: str = "100") -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=[
            LeadBasicInfoField(field_key="cra", label="CRA", value=cra, source_row=3, source_col=2),
            LeadBasicInfoField(field_key="te", label="TE", value=te, source_row=4, source_col=2),
        ],
        materiality=[
            MaterialityCapture(
                field_key="te",
                label="TE",
                workpaper_value=te,
                source_row=4,
                source_col_workpaper=2,
            )
        ],
    )


def _save_sap_workbook(path: Path, sheet_name: str, *, cra: str = "Minimal", te: int = 100, over: str = "否"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(["客户名称", "测试公司", "实体类型", "非复杂实体"])
    ws.append(["年度", "2025", "可容忍误差(TE)", te])
    ws.append(["记账本位币", "CNY", "CRA", cra])
    ws.append([])
    ws.append(["预期", "根据资产类别、原值、使用寿命和残值率形成折旧预期"])
    ws.append(["精确度", "中精度说明，同时模板说明中提到高精确度适用场景"])
    ws.append(["细分", "按资产类别分解"])
    ws.append([])
    ws.append(["偏差阈值", 10])
    ws.append(["实际折旧费用", 95])
    ws.append(["偏差金额", 5])
    ws.append(["偏差是否超过阈值？", over])
    ws.append(["结论", "偏差未超过阈值"])
    wb.save(path)
    wb.close()
    return path


def test_sap_medium_precision_detects_from_sheet_name_even_when_high_text_exists(tmp_path: Path):
    path = _save_sap_workbook(tmp_path / "sap_medium.xlsx", "K.03.1 SAP-中精确度")

    dataset = load_k03_sheets_from_workbook(path)[0]

    assert dataset.execution_path == EXECUTION_PATH_SAP_MEDIUM
    assert dataset.template_type == "sap_medium_precision"
    assert dataset.unsupported_or_later_phase is False


def test_sap_high_precision_detects_from_sheet_name(tmp_path: Path):
    path = _save_sap_workbook(tmp_path / "sap_high.xlsx", "K.03.1 SAP-高精确度", cra="Moderate")

    dataset = load_k03_sheets_from_workbook(path)[0]

    assert dataset.execution_path == EXECUTION_PATH_SAP_HIGH
    assert dataset.template_type == "sap_high_precision"


def test_sap_medium_precision_non_minimal_without_tod_needs_review(tmp_path: Path):
    path = _save_sap_workbook(tmp_path / "sap_medium_non_minimal.xlsx", "K.03.1 SAP-中精确度", cra="Moderate")
    dataset = load_k03_sheets_from_workbook(path)[0]

    issues = run_k03_sap_rules(dataset, lead=_lead(cra="Moderate"), k03_sheets=[dataset])

    assert any(
        issue.rule_id == "sap_precision_selection"
        and issue.severity == Severity.NEED_REVIEW
        for issue in issues
    )


def test_sap_deviation_over_threshold_without_note_fails(tmp_path: Path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.03.1 SAP-高精确度"
    ws.append(["可容忍误差(TE)", 100, "CRA", "Moderate"])
    ws.append(["预期", "根据资产信息形成折旧预期"])
    ws.append(["偏差阈值", 10])
    ws.append(["实际折旧费用", 95])
    ws.append(["偏差金额", 20])
    ws.append(["偏差是否超过阈值？", "是"])
    path = tmp_path / "sap_over.xlsx"
    wb.save(path)
    wb.close()
    dataset = load_k03_sheets_from_workbook(path)[0]

    issues = run_k03_sap_rules(dataset, lead=_lead(cra="Moderate"), k03_sheets=[dataset])

    assert any(
        issue.rule_id == "sap_depreciation_difference"
        and issue.severity == Severity.FAIL
        for issue in issues
    )
