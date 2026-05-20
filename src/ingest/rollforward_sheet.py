"""K.01 后推表解析：表头映射 + 合计行/明细汇总。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl

from ingest.field_mapping import map_headers
from ingest.header_detection import scan_rows_for_headers
from ingest.models import AssetRecord, FieldMapping, SheetKind
from ingest.records import parse_fa_list_rows
from ingest.sheet_loader import find_sheets_by_kind
from ingest.workbook_reader import read_worksheet_rows
from rules.parsing import parse_amount

TOTAL_ROW_PATTERN = re.compile(r"(合计|总计|期末余额|账面余额合计|Grand\s*Total)", re.I)


@dataclass
class RollforwardSheetDataset:
    source_file: str
    source_sheet: str
    header_row: int | None
    mapped_fields: list[FieldMapping]
    detail_records: list[AssetRecord] = field(default_factory=list)
    ending_totals: dict[str, Decimal | None] = field(default_factory=dict)
    total_row: int | None = None
    notes: list[str] = field(default_factory=list)


def _cell_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _row_has_total_label(row: tuple[Any, ...], *, max_cols: int = 6) -> bool:
    for val in row[:max_cols]:
        text = _cell_str(val)
        if text and TOTAL_ROW_PATTERN.search(text):
            return True
    return False


def _amount_at_col(row: tuple[Any, ...], col_index: int) -> Decimal | None:
    if col_index <= 0 or col_index > len(row):
        return None
    return parse_amount(_cell_str(row[col_index - 1]))


def _extract_totals_from_row(
    row: tuple[Any, ...],
    col_by_field: dict[str, int],
) -> dict[str, Decimal | None]:
    totals: dict[str, Decimal | None] = {}
    for field_name in ("original_value", "accumulated_depreciation", "impairment_provision", "net_value"):
        col = col_by_field.get(field_name)
        if col is not None:
            totals[field_name] = _amount_at_col(row, col)
    return totals


def _sum_records(records: list[AssetRecord], field_name: str) -> Decimal | None:
    total = Decimal("0")
    seen = False
    for rec in records:
        val = parse_amount(getattr(rec, field_name, None))
        if val is not None:
            total += val
            seen = True
    return total if seen else None


def parse_rollforward_rows(
    rows: list[tuple[Any, ...]],
    *,
    source_file: str = "",
    source_sheet: str = "",
) -> RollforwardSheetDataset:
    fa_parsed = parse_fa_list_rows(
        rows,
        source_file=source_file,
        source_sheet=source_sheet,
        sheet_kind=SheetKind.ROLLFORWARD,
    )
    header_row, header_cells, _ = scan_rows_for_headers(rows, sheet_kind=SheetKind.ROLLFORWARD)
    mapped_fields, _ = map_headers(header_cells, sheet_kind=SheetKind.ROLLFORWARD) if header_cells else ([], [])
    col_by_field = {m.standard_field: m.column_index for m in mapped_fields}

    ending: dict[str, Decimal | None] = {}
    total_row: int | None = None
    notes: list[str] = []

    if header_row and col_by_field:
        start = header_row
        for r_idx in range(start, len(rows)):
            row = rows[r_idx]
            if row is None or not _row_has_total_label(row):
                continue
            candidate = _extract_totals_from_row(row, col_by_field)
            if any(v is not None for v in candidate.values()):
                ending = candidate
                total_row = r_idx + 1
                break

    if not ending:
        detail = [
            r
            for r in fa_parsed.records
            if any(
                parse_amount(getattr(r, f, None)) is not None
                for f in ("original_value", "accumulated_depreciation", "net_value")
            )
        ]
        if detail:
            ending = {
                "original_value": _sum_records(detail, "original_value"),
                "accumulated_depreciation": _sum_records(detail, "accumulated_depreciation"),
                "impairment_provision": _sum_records(detail, "impairment_provision"),
                "net_value": _sum_records(detail, "net_value"),
            }
            notes.append("ending_from_detail_sum")
    else:
        notes.append("ending_from_total_row")

    return RollforwardSheetDataset(
        source_file=source_file,
        source_sheet=source_sheet,
        header_row=header_row,
        mapped_fields=fa_parsed.mapped_fields or mapped_fields,
        detail_records=fa_parsed.records,
        ending_totals=ending,
        total_row=total_row,
        notes=notes,
    )


def load_rollforward_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 150,
) -> RollforwardSheetDataset:
    path = Path(path)
    if sheet_name:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            rows = read_worksheet_rows(wb[sheet_name], max_rows=max_rows)
        finally:
            wb.close()
        return parse_rollforward_rows(
            rows,
            source_file=str(path),
            source_sheet=sheet_name,
        )

    candidates = find_sheets_by_kind(path, SheetKind.ROLLFORWARD, max_rows=max_rows or 150)
    if not candidates:
        return RollforwardSheetDataset(
            source_file=str(path),
            source_sheet="",
            header_row=None,
            mapped_fields=[],
        )
    chosen = candidates[0]
    return parse_rollforward_rows(
        chosen.rows,
        source_file=str(path),
        source_sheet=chosen.sheet_name,
    )
