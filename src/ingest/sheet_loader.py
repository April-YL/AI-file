"""按 SheetKind 扫描并加载资产类清单（FA list / 新增 / 处置）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl

from ingest.models import SheetKind
from ingest.records import FaListDataset, parse_fa_list_rows
from ingest.sheet_classifier import classify_sheet
from ingest.workbook_reader import read_worksheet_rows


@dataclass
class SheetLoadCandidate:
    sheet_name: str
    kind: SheetKind
    confidence: float
    rows: list[tuple[Any, ...]]


def find_sheets_by_kind(
    path: str | Path,
    kind: SheetKind,
    *,
    max_rows: int | None = 100,
) -> list[SheetLoadCandidate]:
    path = Path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    candidates: list[SheetLoadCandidate] = []
    try:
        for ws in wb.worksheets:
            rows = read_worksheet_rows(ws, max_rows=max_rows)
            detected, confidence, *_ = classify_sheet(ws.title, rows)
            if detected == kind:
                candidates.append(
                    SheetLoadCandidate(
                        sheet_name=ws.title,
                        kind=kind,
                        confidence=confidence,
                        rows=rows,
                    )
                )
    finally:
        wb.close()
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


def load_asset_sheet_from_workbook(
    path: str | Path,
    kind: SheetKind,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = None,
) -> FaListDataset:
    """读取指定类型的资产清单 sheet，输出统一 FaListDataset / AssetRecord。"""
    path = Path(path)
    candidates = find_sheets_by_kind(path, kind, max_rows=max_rows or 100)

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
                sheet_kind=kind,
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
        sheet_kind=kind,
    )


def load_all_sheets_of_kind(
    path: str | Path,
    kind: SheetKind,
    *,
    max_rows: int | None = 100,
) -> list[FaListDataset]:
    datasets: list[FaListDataset] = []
    for cand in find_sheets_by_kind(path, kind, max_rows=max_rows):
        datasets.append(
            parse_fa_list_rows(
                cand.rows,
                source_file=str(path),
                source_sheet=cand.sheet_name,
                sheet_kind=kind,
            )
        )
    return datasets
