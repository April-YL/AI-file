from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl

from ingest.models import SheetKind
from ingest.sheet_classifier import classify_sheet
from ingest.workbook_reader import read_worksheet_rows


@dataclass
class PspProgramRow:
    """汇总页单行程序（PSP）记录。"""

    procedure_name: str
    sheet_ref: str | None
    execution_status: str | None
    waiver_reason: str | None
    notes: str | None
    source_row: int
    is_psp: bool = False


@dataclass
class SummarySheetDataset:
    source_file: str
    source_sheet: str
    header_row: int | None
    programs: list[PspProgramRow]


_PROCEDURE_HEADERS = ("程序", "程序名称", "审计程序", "底稿程序")
_SHEET_HEADERS = ("工作表", "sheet", "底稿索引", "索引")
_EXEC_HEADERS = ("是否执行", "执行", "执行与否", "是否已执行")
_WAIVER_HEADERS = ("不执行原因", "拒绝理由", "不执行的理由", "未执行原因", "拒绝执行理由")
_NOTES_HEADERS = ("注意事项", "备注", "说明")
_PSP_MARKERS = ("psp", "ps p", "显著风险", "specific performance")


def _cell_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _norm_header(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def _match_column(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    for idx, h in enumerate(headers):
        nh = _norm_header(h)
        for c in candidates:
            nc = _norm_header(c)
            if nh == nc or nc in nh or nh in nc:
                return idx
    return None


def _detect_header_row(rows: list[tuple[Any, ...]], max_scan: int = 30) -> tuple[int | None, list[str]]:
    limit = min(len(rows), max_scan)
    for r_idx in range(limit):
        row = rows[r_idx]
        if not row:
            continue
        headers = [_cell_str(c) or "" for c in row]
        if _match_column(headers, _PROCEDURE_HEADERS) is not None and (
            _match_column(headers, _EXEC_HEADERS) is not None
            or _match_column(headers, _WAIVER_HEADERS) is not None
        ):
            return r_idx + 1, headers
    return None, []


def _is_psp_row(procedure_name: str, notes: str | None) -> bool:
    blob = f"{procedure_name} {notes or ''}".lower()
    return any(m in blob for m in _PSP_MARKERS) or "psp" in blob.replace(" ", "")


def parse_summary_rows(
    rows: list[tuple[Any, ...]],
    *,
    source_file: str = "",
    source_sheet: str = "汇总",
) -> SummarySheetDataset:
    header_row, headers = _detect_header_row(rows)
    if not header_row or not headers:
        return SummarySheetDataset(
            source_file=source_file,
            source_sheet=source_sheet,
            header_row=None,
            programs=[],
        )

    col_proc = _match_column(headers, _PROCEDURE_HEADERS)
    col_sheet = _match_column(headers, _SHEET_HEADERS)
    col_exec = _match_column(headers, _EXEC_HEADERS)
    col_waiver = _match_column(headers, _WAIVER_HEADERS)
    col_notes = _match_column(headers, _NOTES_HEADERS)

    programs: list[PspProgramRow] = []
    start_idx = header_row
    for r_idx in range(start_idx, len(rows)):
        row = rows[r_idx]
        if row is None or not any(_cell_str(c) for c in row):
            continue
        cells = list(row)

        def _get(col: int | None) -> str | None:
            if col is None or col >= len(cells):
                return None
            return _cell_str(cells[col])

        proc = _get(col_proc)
        if not proc:
            continue
        if _norm_header(proc) in ("程序", "程序名称", "审计程序"):
            continue

        sheet_ref = _get(col_sheet)
        exec_status = _get(col_exec)
        waiver = _get(col_waiver)
        notes = _get(col_notes)
        programs.append(
            PspProgramRow(
                procedure_name=proc,
                sheet_ref=sheet_ref,
                execution_status=exec_status,
                waiver_reason=waiver,
                notes=notes,
                source_row=r_idx + 1,
                is_psp=_is_psp_row(proc, notes),
            )
        )

    return SummarySheetDataset(
        source_file=source_file,
        source_sheet=source_sheet,
        header_row=header_row,
        programs=programs,
    )


def find_summary_sheets(
    path: str | Path,
    *,
    max_rows: int | None = 200,
) -> list[tuple[str, float, list[tuple[Any, ...]]]]:
    path = Path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    found: list[tuple[str, float, list[tuple[Any, ...]]]] = []
    try:
        for ws in wb.worksheets:
            rows = read_worksheet_rows(ws, max_rows=max_rows)
            kind, confidence, *_ = classify_sheet(ws.title, rows)
            if kind == SheetKind.SUMMARY:
                found.append((ws.title, confidence, rows))
    finally:
        wb.close()
    found.sort(key=lambda x: x[1], reverse=True)
    return found


def load_summary_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 200,
) -> SummarySheetDataset:
    path = Path(path)
    candidates = find_summary_sheets(path, max_rows=max_rows)

    if sheet_name:
        match = next((c for c in candidates if c[0] == sheet_name), None)
        if match is None:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                ws = wb[sheet_name]
                rows = read_worksheet_rows(ws, max_rows=max_rows)
            finally:
                wb.close()
            return parse_summary_rows(
                rows, source_file=str(path), source_sheet=sheet_name
            )
        name, _, rows = match
        return parse_summary_rows(rows, source_file=str(path), source_sheet=name)

    if candidates:
        name, _, rows = candidates[0]
        return parse_summary_rows(rows, source_file=str(path), source_sheet=name)

    return SummarySheetDataset(
        source_file=str(path),
        source_sheet="",
        header_row=None,
        programs=[],
    )
