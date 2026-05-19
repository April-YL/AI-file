from pathlib import Path

import openpyxl
import pytest

from ingest.records import (
    find_fa_list_sheets,
    load_fa_list_csv,
    load_fa_list_from_workbook,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def fa_list_xlsx(tmp_path: Path) -> Path:
    """由 fa_list_mixed.csv 生成最小 Excel 底稿（FA list sheet）。"""
    csv_path = FIXTURES / "fa_list_mixed.csv"
    xlsx_path = tmp_path / "fa_list_mixed.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FA list"
    with csv_path.open(encoding="utf-8-sig") as f:
        for line in f:
            ws.append(line.strip().split(","))
    wb.save(xlsx_path)
    wb.close()
    return xlsx_path


def test_find_fa_list_sheets(fa_list_xlsx: Path):
    candidates = find_fa_list_sheets(fa_list_xlsx)
    assert len(candidates) >= 1
    assert candidates[0].sheet_name == "FA list"
    assert candidates[0].confidence > 0.5


def test_load_fa_list_from_workbook_matches_csv(fa_list_xlsx: Path):
    from_csv = load_fa_list_csv(FIXTURES / "fa_list_mixed.csv")
    from_xlsx = load_fa_list_from_workbook(fa_list_xlsx)

    assert from_xlsx.source_sheet == "FA list"
    assert len(from_xlsx.records) == len(from_csv.records)
    assert from_xlsx.records[0].asset_id == "FA-TEST-001"
    assert from_xlsx.mapped_fields


def test_load_fa_list_from_workbook_explicit_sheet(fa_list_xlsx: Path):
    dataset = load_fa_list_from_workbook(fa_list_xlsx, sheet_name="FA list")
    assert len(dataset.records) == 6


def test_load_fa_list_from_workbook_no_fa_list(tmp_path: Path):
    xlsx = tmp_path / "empty.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws.append(["项目", "金额"])
    ws.append(["合计", 100])
    wb.save(xlsx)
    wb.close()

    dataset = load_fa_list_from_workbook(xlsx)
    assert dataset.records == []
    assert dataset.source_sheet == ""
