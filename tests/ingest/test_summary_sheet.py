from pathlib import Path

import openpyxl
import pytest

from ingest.summary_sheet import load_summary_from_workbook, parse_summary_rows

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def summary_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "wb_summary.xlsx"
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "汇总"
    ws_sum.append(["程序", "工作表", "是否执行", "不执行原因"])
    ws_sum.append(["K.01 后推", "K.01", "是", ""])
    ws_sum.append(["PSP-折旧测试", "K.03.1", "否", ""])
    ws_sum.append(["PSP-新增", "K.02.1", "否", "已提供合同约定的购置清单"])
    ws_fa = wb.create_sheet("FA list")
    ws_fa.append(["固定资产编号", "固定资产名称", "原值", "累计折旧", "净值"])
    ws_fa.append(["FA-TEST-001", "设备", 1000, 100, 900])
    wb.save(path)
    wb.close()
    return path


def test_parse_summary_rows():
    rows = [
        ("程序", "工作表", "是否执行", "不执行原因"),
        ("PSP-测试", "K.03.1", "否", ""),
    ]
    ds = parse_summary_rows(rows, source_sheet="汇总")
    assert ds.header_row == 1
    assert len(ds.programs) == 1
    assert ds.programs[0].is_psp is True
    roles = {b.role for b in ds.column_bindings}
    assert "procedure" in roles
    assert "execution_status" in roles
    assert ds.last_data_row == 2


def test_parse_summary_skips_title_rows():
    rows = [
        ("固定资产审计程序汇总表", None, None, None),
        (),
        ("程序", "工作表", "是否执行", "不执行原因"),
        ("K.01 后推", "K.01", "是", ""),
    ]
    ds = parse_summary_rows(rows, source_sheet="汇总")
    assert ds.header_row == 3
    assert len(ds.programs) == 1
    assert ds.programs[0].procedure_name == "K.01 后推"


def test_parse_summary_stops_after_blank_gap():
    rows = [
        ("程序", "是否执行", "不执行原因"),
        ("A", "是", ""),
        (),
        (),
        (),
        ("脚注或其它",),
    ]
    ds = parse_summary_rows(rows, source_sheet="汇总")
    assert len(ds.programs) == 1
    assert "main_table_end_after_blank_rows" in "".join(ds.notes)


def test_load_summary_from_workbook(summary_xlsx: Path):
    ds = load_summary_from_workbook(summary_xlsx)
    assert ds.source_sheet == "汇总"
    assert len(ds.programs) == 3
    psp = [p for p in ds.programs if p.is_psp]
    assert len(psp) == 2


def test_parse_summary_swp_standard_layout():
    """K1 SWP：B/C 程序、F 程序页、G/H/I 与案例库汇总一致。"""
    rows = [
        ("", "K.00", "K.00 Lead Sheet", "", "", "程序页", "执行", "不执行的原因", "注意事项"),
        ("", "1", "获取和编制固定资产两期变动", "", "", "K.00 Lead Sheet", "是", "", "note1"),
        ("", "K.01", "K.01 Agree SL to GL", "", "", "程序页", "执行", "不执行的原因", "注意事项"),
        ("", "1", "获取固定资产后推表", "", "", "K.01 Agree SL to GL", "否", "当期无此类交易", ""),
    ]
    ds = parse_summary_rows(rows, source_sheet="汇总 ")
    assert ds.layout == "swp"
    assert ds.programs[0].procedure_name.startswith("1 ")
    assert ds.programs[0].execution_status == "是"
    assert ds.programs[-1].execution_status == "否"
    assert "交易" in (ds.programs[-1].waiver_reason or "")
    roles = {b.role for b in ds.column_bindings}
    assert "procedure_code" in roles
    assert "sheet_ref" in roles


def test_parse_summary_swp_keeps_rows_with_only_sheet_ref():
    rows = [
        ("", "K.02", "K.02.1 新增测试", "", "", "程序页", "执行", "不执行的原因", "注意事项"),
        ("", "1", "获取新增清单", "", "", "新增清单", "", "", ""),
        ("", "2", "执行新增测试", "", "", "K.02.1 新增测试", "", "", ""),
        ("", "", "", "", "", "K.02.1a 新增选样输出", "", "", ""),
    ]
    ds = parse_summary_rows(rows, source_sheet="汇总 ")
    assert ds.layout == "swp"
    assert len(ds.programs) == 3
    assert ds.programs[-1].sheet_ref == "K.02.1a 新增选样输出"
    assert ds.programs[-1].procedure_name == "K.02.1a 新增选样输出"
