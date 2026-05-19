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


def test_load_summary_from_workbook(summary_xlsx: Path):
    ds = load_summary_from_workbook(summary_xlsx)
    assert ds.source_sheet == "汇总"
    assert len(ds.programs) == 3
    psp = [p for p in ds.programs if p.is_psp]
    assert len(psp) == 2
