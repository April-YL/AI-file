from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ingest.field_mapping import map_headers
from ingest.header_detection import scan_rows_for_headers
from ingest.models import AssetRecord, FieldMapping, SheetKind

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
        records.append(_build_record(row_values, col_by_field, source_row=r_idx + 1))

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
