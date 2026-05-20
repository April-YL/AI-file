from pathlib import Path

import openpyxl
import pytest

from ingest.lead_sheet import load_lead_from_workbook, parse_lead_sheet_rows

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def lead_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "lead_wb.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.00 Lead Sheet"
    ws["A1"] = "项目"
    ws["B1"] = "底稿值"
    ws["C1"] = "Canvas最终"
    ws["A2"] = "可容忍误差"
    ws["B2"] = "100000"
    ws["C2"] = "100000"
    ws["A3"] = "名义金额"
    ws["B3"] = "50000"
    ws["C3"] = "50000"
    ws["A4"] = "计划重要性"
    ws["B4"] = "200000"
    ws["C4"] = "200000"
    ws["A6"] = "认定"
    ws["B6"] = "CRA"
    ws["C6"] = "TT"
    ws["A7"] = "固定资产"
    ws["B7"] = "High"
    ws["C7"] = "150000"
    ws["A8"] = "存货"
    ws["B8"] = "Moderate"
    ws["C8"] = "80000"
    wb.save(path)
    wb.close()
    return path


def test_parse_materiality_and_cra(lead_xlsx: Path):
    ds = load_lead_from_workbook(lead_xlsx)
    assert ds.source_sheet == "K.00 Lead Sheet"
    keys = {m.field_key: m for m in ds.materiality}
    assert keys["te"].workpaper_value == "100000"
    assert keys["te"].canvas_value == "100000"
    assert len(ds.cra_rows) >= 1
    fa_row = next(r for r in ds.cra_rows if "固定资产" in r.assertion)
    assert fa_row.cra == "High"
    assert fa_row.tt == "150000"
