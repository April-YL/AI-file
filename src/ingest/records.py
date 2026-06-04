from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl

from ingest.field_mapping import map_headers
from ingest.header_detection import scan_rows_for_headers
from ingest.models import AssetRecord, FieldMapping, SheetKind
from ingest.sheet_classifier import classify_sheet
from ingest.workbook_reader import read_worksheet_rows

_RECORD_FIELDS = (
    "asset_id",
    "asset_name",
    "asset_category",
    "start_date",
    "useful_life_months",
    "salvage_rate",
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "net_value",
    "addition_method",
)


@dataclass
class FaListDataset:
    source_file: str
    source_sheet: str
    mapped_fields: list[FieldMapping]
    records: list[AssetRecord]


def _cell_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _build_record(
    row_values: dict[str, Any],
    col_by_field: dict[str, int],
    source_row: int,
) -> AssetRecord:
    data: dict[str, Any] = {"source_row": source_row}
    for field_name in _RECORD_FIELDS:
        col = col_by_field.get(field_name)
        if col is None:
            data[field_name] = None
        else:
            data[field_name] = _cell_str(row_values.get(col))
    return AssetRecord(**data)


def _is_non_asset_summary_row(record: AssetRecord) -> bool:
    """过滤 FA list 尾部重分类/合计等非资产明细行。"""
    aid = (record.asset_id or "").strip()
    name = (record.asset_name or "").strip()
    if not aid:
        return False
    summary_tokens = ("资产类别重分类", "重分类", "合计", "小计", "总计")
    if any(token in aid for token in summary_tokens) and not name:
        return True
    return aid in {"-", "—", "N/A", "NA"}


def parse_fa_list_rows(
    rows: list[tuple[Any, ...]],
    *,
    source_file: str = "",
    source_sheet: str = "FA list",
    sheet_kind: SheetKind = SheetKind.FA_LIST,
) -> FaListDataset:
    header_row, header_cells, _ = scan_rows_for_headers(rows, sheet_kind=sheet_kind)
    if not header_cells:
        return FaListDataset(
            source_file=source_file,
            source_sheet=source_sheet,
            mapped_fields=[],
            records=[],
        )

    mapped_fields, _ = map_headers(header_cells, sheet_kind=sheet_kind)
    col_by_field = {m.standard_field: m.column_index for m in mapped_fields}

    records: list[AssetRecord] = []
    start_idx = (header_row or 1)
    for r_idx in range(start_idx, len(rows)):
        row = rows[r_idx]
        if row is None:
            continue
        row_values = {i + 1: row[i] if i < len(row) else None for i in range(len(row))}
        if not any(v is not None and str(v).strip() for v in row_values.values()):
            continue
        record = _build_record(row_values, col_by_field, source_row=r_idx + 1)
        if _is_non_asset_summary_row(record):
            continue
        records.append(record)

    return FaListDataset(
        source_file=source_file,
        source_sheet=source_sheet,
        mapped_fields=mapped_fields,
        records=records,
    )


def load_fa_list_csv(path: str | Path, *, source_sheet: str = "FA list") -> FaListDataset:
    path = Path(path)
    rows: list[tuple[Any, ...]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(tuple(row))
    dataset = parse_fa_list_rows(
        rows,
        source_file=str(path),
        source_sheet=source_sheet,
    )
    return dataset


@dataclass
class FaListSheetCandidate:
    sheet_name: str
    confidence: float
    rows: list[tuple[Any, ...]]


def find_fa_list_sheets(
    path: str | Path,
    *,
    max_rows: int | None = None,
) -> list[FaListSheetCandidate]:
    """扫描工作簿，返回识别为 FA list 的工作表（按 confidence 降序）。"""
    path = Path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    candidates: list[FaListSheetCandidate] = []
    try:
        for ws in wb.worksheets:
            rows = read_worksheet_rows(ws, max_rows=max_rows)
            kind, confidence, *_ = classify_sheet(ws.title, rows)
            if kind == SheetKind.FA_LIST:
                candidates.append(
                    FaListSheetCandidate(
                        sheet_name=ws.title,
                        confidence=confidence,
                        rows=rows,
                    )
                )
    finally:
        wb.close()
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


def load_fa_list_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = None,
) -> FaListDataset:
    """从 Excel 底稿读取 FA list 工作表并解析为 AssetRecord 列表。"""
    path = Path(path)
    candidates = find_fa_list_sheets(path, max_rows=max_rows)

    if sheet_name:
        match = next((c for c in candidates if c.sheet_name == sheet_name), None)
        if match is None:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                ws = wb[sheet_name]
                rows = read_worksheet_rows(ws, max_rows=max_rows)
            finally:
                wb.close()
            return parse_fa_list_rows(
                rows,
                source_file=str(path),
                source_sheet=sheet_name,
            )
        chosen = match
    elif candidates:
        chosen = candidates[0]
    else:
        return FaListDataset(
            source_file=str(path),
            source_sheet="",
            mapped_fields=[],
            records=[],
        )

    return parse_fa_list_rows(
        chosen.rows,
        source_file=str(path),
        source_sheet=chosen.sheet_name,
    )
