from __future__ import annotations

from pathlib import Path

import openpyxl

from ingest.k03_sheet import EXECUTION_PATH_TOD_SAMPLING, load_k03_sheets_from_workbook
from ingest.lead_sheet import LeadBasicInfoField, LeadSheetDataset, MaterialityCapture
from rules.k03_tod_sampling import run_k03_tod_sampling_rules
from rules.models import Severity


def _lead(te: str = "100", sad: str = "5") -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=[
            LeadBasicInfoField(field_key="te", label="TE", value=te, source_row=3, source_col=2),
            LeadBasicInfoField(field_key="sad", label="SAD", value=sad, source_row=4, source_col=2),
        ],
        materiality=[
            MaterialityCapture(
                field_key="te",
                label="TE",
                workpaper_value=te,
                source_row=3,
                source_col_workpaper=2,
            )
        ],
    )


def _save_sampling_workbook(path: Path, *, conclusion: str | None = "样本测试未见重大差异") -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.03.2 折旧测试TOD-抽样"
    ws.append(["折旧费用总体", 1000])
    ws.append(["Breakdown中折旧计提金额", 1000])
    ws.append(["减：测试的关键项目", 100])
    ws.append(["剩余总体", 900])
    ws.append(["关键项目", "选择大额资产作为关键项目"])
    ws.append([])
    ws.append(["样本数量", "样本类型", "固定资产类别", "固定资产编号", "固定资产名称", "原值", "可折旧金额", "使用寿命(月)"])
    ws.append([1, "随机", "设备", "FA-TEST-001", "设备A", 1000, 900, 60])
    if conclusion is not None:
        ws.append(["结论", conclusion])
    out = wb.create_sheet("K.03.2a 折旧选样输出")
    out.append(["可容忍误差", 100])
    out.append(["抽样货币单元", "本期计提折旧"])
    out.append(["总体金额", 1000])
    out.append(["关键项目数量", 1])
    out.append(["关键项目金额", 100])
    out.append(["双重目的", "否"])
    out.append(["高估", "是"])
    out.append(["保证水平", "几乎没有"])
    out.append(["样本池", 900])
    out.append(["预期错报", "否"])
    out.append(["抽样方法", "随机抽样 (Random)"])
    wb.save(path)
    wb.close()
    return path


def test_tod_sampling_sheet_name_overrides_by_item_like_headers(tmp_path: Path):
    path = _save_sampling_workbook(tmp_path / "tod_sampling.xlsx")

    datasets = load_k03_sheets_from_workbook(path)
    main = next(item for item in datasets if item.sheet_name == "K.03.2 折旧测试TOD-抽样")

    assert main.execution_path == EXECUTION_PATH_TOD_SAMPLING
    assert main.template_type == "tod_sampling"


def test_tod_sampling_wrong_sampling_currency_fails(tmp_path: Path):
    path = _save_sampling_workbook(tmp_path / "tod_bad_currency.xlsx")
    wb = openpyxl.load_workbook(path)
    ws = wb["K.03.2a 折旧选样输出"]
    ws["B2"] = "原值"
    wb.save(path)
    wb.close()
    datasets = load_k03_sheets_from_workbook(path)
    main = next(item for item in datasets if item.template_type == "tod_sampling")
    output = next(item for item in datasets if item.template_type == "tod_sampling_output")

    issues = run_k03_tod_sampling_rules(main, sample_output=output, lead=_lead())

    assert any(
        issue.rule_id == "depreciation_tod_sampling"
        and issue.severity == Severity.FAIL
        for issue in issues
    )


def test_tod_sampling_missing_conclusion_needs_review(tmp_path: Path):
    path = _save_sampling_workbook(tmp_path / "tod_no_conclusion.xlsx", conclusion=None)
    datasets = load_k03_sheets_from_workbook(path)
    main = next(item for item in datasets if item.template_type == "tod_sampling")
    output = next(item for item in datasets if item.template_type == "tod_sampling_output")

    issues = run_k03_tod_sampling_rules(main, sample_output=output, lead=_lead())

    assert any(
        issue.rule_id == "depreciation_tod_difference"
        and issue.severity == Severity.NEED_REVIEW
        for issue in issues
    )
