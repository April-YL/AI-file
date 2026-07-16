"""按 SheetKind 扫描并加载资产类清单（FA list / 新增 / 处置）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl

from ingest.models import SheetKind, SheetResolutionDecision
from ingest.records import FaListDataset, parse_fa_list_rows
from ingest.sheet_classifier import classify_sheet, score_by_name
from ingest.sheet_period_routing import choose_sheet_candidate, sort_sheet_candidates
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
            name_kind, *_ = score_by_name(ws.title)
            if name_kind == SheetKind.SKIP:
                continue
            preview_rows = read_worksheet_rows(ws, max_rows=max_rows)
            detected, confidence, *_ = classify_sheet(ws.title, preview_rows)
            if detected == kind:
                rows = (
                    read_worksheet_rows(ws, max_rows=None)
                    if kind == SheetKind.ADDITION_LIST
                    else preview_rows
                )
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
    return sort_sheet_candidates(
        candidates,
        name=lambda c: c.sheet_name,
        confidence=lambda c: c.confidence,
        source_path=path,
    )


def load_asset_sheet_from_workbook(
    path: str | Path,
    kind: SheetKind,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = None,
    sheet_resolution: SheetResolutionDecision | None = None,
) -> FaListDataset:
    """读取指定类型的资产清单 sheet，输出统一 FaListDataset / AssetRecord。"""
    path = Path(path)
    if sheet_name:
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
            sheet_resolution=sheet_resolution,
        )

    candidates = find_sheets_by_kind(path, kind, max_rows=max_rows or 100)

    if candidates:
        chosen = choose_sheet_candidate(
            candidates,
            name=lambda c: c.sheet_name,
            confidence=lambda c: c.confidence,
            source_path=path,
        )
        assert chosen is not None
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
