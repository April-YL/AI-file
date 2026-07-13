from __future__ import annotations

from pathlib import Path

import openpyxl

from ingest.k03_sheet import (
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING,
    EXECUTION_PATH_TOD_SAMPLING,
    K03ComponentSheet,
    K03ExecutionProfile,
    K03LeadLinkage,
    K03SheetDataset,
    load_k03_sheets_from_workbook,
)
from ingest.lead_sheet import LeadBasicInfoField, LeadSheetDataset, MaterialityCapture
from rules.execution_recorder import (
    STATUS_DATA_INSUFFICIENT,
    STATUS_EXECUTED,
    STATUS_NOT_APPLICABLE,
    RuleExecutionRecorder,
)
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


def _profile(
    dataset: K03SheetDataset,
    *,
    cra: str | None,
    with_tod: bool = False,
) -> K03ExecutionProfile:
    role = "sap_high" if dataset.execution_path == EXECUTION_PATH_SAP_HIGH else "sap_medium"
    components = {
        role: [
            K03ComponentSheet(
                role=role,
                sheet_name=dataset.sheet_name,
                execution_path=dataset.execution_path,
                template_type=dataset.template_type,
            )
        ]
    }
    primary_path = dataset.execution_path
    if with_tod:
        components["tod_sampling"] = [
            K03ComponentSheet(
                role="tod_sampling",
                sheet_name="K.03.2 TOD sampling",
                execution_path=EXECUTION_PATH_TOD_SAMPLING,
                template_type="tod_sampling",
            )
        ]
        primary_path = EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING
    return K03ExecutionProfile(
        primary_depreciation_path=primary_path,
        executed_depreciation_paths=[
            dataset.execution_path,
            *([EXECUTION_PATH_TOD_SAMPLING] if with_tod else []),
        ],
        component_sheets=components,
        lead_linkage=K03LeadLinkage(
            assertion="V/M",
            cra=cra,
            source_row=25,
            cra_cell="C25",
            source="lead_vm_assertion",
        ),
    )


def _ledger_items(recorder: RuleExecutionRecorder) -> dict[str, dict]:
    return {item["rule_id"]: item for item in recorder.to_ledger()["items"]}


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

    issues = run_k03_sap_rules(
        dataset,
        lead=_lead(cra="Moderate"),
        k03_sheets=[dataset],
        k03_execution_profile=_profile(dataset, cra="Moderate"),
    )

    assert any(
        issue.rule_id == "sap_precision_selection"
        and issue.severity == Severity.NEED_REVIEW
        for issue in issues
    )


def test_sap_medium_uses_lead_vm_cra_not_template_minimal(tmp_path: Path):
    path = _save_sap_workbook(
        tmp_path / "sap_medium_preset_minimal.xlsx",
        "K.03.1 SAP-中精确度",
        cra="Minimal",
    )
    dataset = load_k03_sheets_from_workbook(path)[0]

    issues = run_k03_sap_rules(
        dataset,
        lead=_lead(cra="Moderate"),
        k03_execution_profile=_profile(dataset, cra="Moderate"),
    )

    assert any(issue.rule_id == "sap_precision_selection" for issue in issues)
    assert not any(issue.rule_id == "sap_high_cra_consistency" for issue in issues)


def test_sap_medium_non_minimal_with_tod_is_allowed(tmp_path: Path):
    path = _save_sap_workbook(
        tmp_path / "sap_medium_with_tod.xlsx",
        "K.03.1 SAP-中精确度",
        cra="Minimal",
    )
    dataset = load_k03_sheets_from_workbook(path)[0]

    issues = run_k03_sap_rules(
        dataset,
        lead=_lead(cra="Moderate"),
        k03_execution_profile=_profile(dataset, cra="Moderate", with_tod=True),
    )

    assert not any(issue.rule_id == "sap_precision_selection" for issue in issues)


def test_sap_te_consistency_has_independent_rule_and_ledger_status(tmp_path: Path):
    path = _save_sap_workbook(
        tmp_path / "sap_bad_te.xlsx",
        "K.03.1 SAP-高精确度",
        cra="Moderate",
        te=90,
    )
    dataset = load_k03_sheets_from_workbook(path)[0]
    recorder = RuleExecutionRecorder()

    issues = run_k03_sap_rules(
        dataset,
        lead=_lead(cra="Moderate", te="100"),
        k03_execution_profile=_profile(dataset, cra="Moderate"),
        recorder=recorder,
    )

    assert any(
        issue.rule_id == "sap_te_consistency" and issue.severity == Severity.FAIL
        for issue in issues
    )
    assert _ledger_items(recorder)["sap_te_consistency"]["status"] == STATUS_EXECUTED


def test_sap_high_cra_consistency_compares_lead_vm_cra(tmp_path: Path):
    path = _save_sap_workbook(
        tmp_path / "sap_bad_cra.xlsx",
        "K.03.1 SAP-高精确度",
        cra="Moderate",
    )
    dataset = load_k03_sheets_from_workbook(path)[0]

    issues = run_k03_sap_rules(
        dataset,
        lead=_lead(cra="Low"),
        k03_execution_profile=_profile(dataset, cra="Low"),
    )

    assert any(
        issue.rule_id == "sap_high_cra_consistency" and issue.severity == Severity.FAIL
        for issue in issues
    )


def test_sap_missing_inputs_are_not_recorded_as_executed(tmp_path: Path):
    path = _save_sap_workbook(
        tmp_path / "sap_missing_inputs.xlsx",
        "K.03.1 SAP-高精确度",
        cra="Moderate",
    )
    dataset = load_k03_sheets_from_workbook(path)[0]
    dataset.summary.pop("sap_te", None)
    dataset.summary.pop("sap_cra", None)
    recorder = RuleExecutionRecorder()

    run_k03_sap_rules(
        dataset,
        lead=_lead(cra="Moderate"),
        k03_execution_profile=_profile(dataset, cra=None),
        recorder=recorder,
    )

    ledger = _ledger_items(recorder)
    assert ledger["sap_precision_selection"]["status"] == STATUS_DATA_INSUFFICIENT
    assert ledger["sap_te_consistency"]["status"] == STATUS_DATA_INSUFFICIENT
    assert ledger["sap_high_cra_consistency"]["status"] == STATUS_DATA_INSUFFICIENT


def test_sap_high_cra_rule_is_not_applicable_to_medium_sap(tmp_path: Path):
    path = _save_sap_workbook(
        tmp_path / "sap_medium_na.xlsx",
        "K.03.1 SAP-中精确度",
    )
    dataset = load_k03_sheets_from_workbook(path)[0]
    recorder = RuleExecutionRecorder()

    run_k03_sap_rules(
        dataset,
        lead=_lead(),
        k03_execution_profile=_profile(dataset, cra="Minimal"),
        recorder=recorder,
    )

    assert (
        _ledger_items(recorder)["sap_high_cra_consistency"]["status"]
        == STATUS_NOT_APPLICABLE
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

    issues = run_k03_sap_rules(
        dataset,
        lead=_lead(cra="Moderate"),
        k03_sheets=[dataset],
        k03_execution_profile=_profile(dataset, cra="Moderate"),
    )

    assert any(
        issue.rule_id == "sap_depreciation_difference"
        and issue.severity == Severity.FAIL
        for issue in issues
    )
