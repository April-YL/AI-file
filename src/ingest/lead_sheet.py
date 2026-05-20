from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

from ingest.models import SheetKind
from ingest.sheet_classifier import classify_sheet, score_by_name
from ingest.workbook_reader import read_worksheet_rows


@dataclass
class MaterialityCapture:
    """PM/TE/SAD 等重要性参数摘录。"""

    field_key: str
    label: str
    workpaper_value: str | None = None
    canvas_value: str | None = None
    source_row: int | None = None
    source_col_workpaper: int | None = None
    source_col_canvas: int | None = None

    def cell_ref_workpaper(self, sheet_name: str) -> str | None:
        if self.source_row and self.source_col_workpaper:
            return f"{sheet_name}!{get_column_letter(self.source_col_workpaper)}{self.source_row}"
        return None

    def cell_ref_canvas(self, sheet_name: str) -> str | None:
        if self.source_row and self.source_col_canvas:
            return f"{sheet_name}!{get_column_letter(self.source_col_canvas)}{self.source_row}"
        return None

    def to_dict(self, sheet_name: str) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "label": self.label,
            "workpaper_value": self.workpaper_value,
            "canvas_or_external_value": self.canvas_value,
            "workpaper_cell": self.cell_ref_workpaper(sheet_name),
            "canvas_cell": self.cell_ref_canvas(sheet_name),
            "compare_status": "pending_manual",
        }


@dataclass
class CraAssertionRow:
    """认定级 CRA / TT 摘录。"""

    assertion: str
    cra: str | None = None
    tt: str | None = None
    source_row: int | None = None
    source_col_assertion: int | None = None
    source_col_cra: int | None = None
    source_col_tt: int | None = None

    def to_dict(self, sheet_name: str) -> dict[str, Any]:
        def ref(col: int | None) -> str | None:
            if self.source_row and col:
                return f"{sheet_name}!{get_column_letter(col)}{self.source_row}"
            return None

        return {
            "assertion": self.assertion,
            "cra": self.cra,
            "tt": self.tt,
            "assertion_cell": ref(self.source_col_assertion),
            "cra_cell": ref(self.source_col_cra),
            "tt_cell": ref(self.source_col_tt),
            "compare_status": "pending_manual",
        }


@dataclass
class LeadSheetDataset:
    source_file: str
    source_sheet: str
    materiality: list[MaterialityCapture] = field(default_factory=list)
    cra_rows: list[CraAssertionRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def has_materiality_data(self) -> bool:
        return any(
            c.workpaper_value or c.canvas_value for c in self.materiality
        )

    def has_cra_data(self) -> bool:
        return len(self.cra_rows) > 0


_MATERIALITY_PATTERNS: dict[str, tuple[str, ...]] = {
    "pm": ("计划重要性", "pm", "planningmateriality", "重要性pm"),
    "te": ("可容忍误差", "te", "tolerableerror", "可容忍错报"),
    "sad": ("名义金额", "sad", "明显微小错报", "summaryauditdifference"),
}

_CANVAS_HEADER_HINTS = ("canvas", "a3", "外出取数", "系统", "最终", "canvasa3")

_CRA_HEADER_HINTS = ("cra", "combinedrisk", "风险", "风险评估")
_TT_HEADER_HINTS = ("tt", "测试阈值", "threshold")
_ASSERTION_HEADER_HINTS = ("认定", "相关认定", "账户", "assertion")


def _cell_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-（）()]", "", text.lower())


def _get_cell(rows: list[tuple[Any, ...]], row_idx: int, col_idx: int) -> str | None:
    if row_idx < 0 or row_idx >= len(rows):
        return None
    row = rows[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return None
    return _cell_str(row[col_idx])


def _label_matches(cell_norm: str, patterns: tuple[str, ...]) -> bool:
    if len(cell_norm) > 40:
        return False
    for p in patterns:
        pn = _norm(p)
        if len(pn) <= 3:
            if cell_norm == pn:
                return True
            continue
        if cell_norm == pn or pn in cell_norm or cell_norm in pn:
            return True
    return False


def _is_probable_value(text: str) -> bool:
    n = _norm(text)
    if _label_matches(n, _MATERIALITY_PATTERNS.get("te", ())):
        return False
    if _label_matches(n, _MATERIALITY_PATTERNS.get("pm", ())):
        return False
    if _label_matches(n, _MATERIALITY_PATTERNS.get("sad", ())):
        return False
    if n in ("认定", "cra", "tt", "canvas", "底稿值", "参考"):
        return False
    return True


def _find_canvas_column(rows: list[tuple[Any, ...]], scan_rows: int = 25) -> int | None:
    for r in range(min(scan_rows, len(rows))):
        row = rows[r]
        for c, val in enumerate(row):
            text = _cell_str(val)
            if not text:
                continue
            n = _norm(text)
            if any(h in n for h in _CANVAS_HEADER_HINTS):
                return c
    return None


def _extract_materiality(
    rows: list[tuple[Any, ...]],
    sheet_name: str,
) -> list[MaterialityCapture]:
    canvas_col = _find_canvas_column(rows)
    found: dict[str, MaterialityCapture] = {}

    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            text = _cell_str(val)
            if not text:
                continue
            n = _norm(text)
            for field_key, patterns in _MATERIALITY_PATTERNS.items():
                if not _label_matches(n, patterns):
                    continue
                cap = found.get(field_key)
                if cap is None:
                    cap = MaterialityCapture(
                        field_key=field_key,
                        label=text,
                    )
                    found[field_key] = cap
                cap.source_row = r + 1
                for dc in (1, 2, 3):
                    v = _get_cell(rows, r, c + dc)
                    if v and _is_probable_value(v):
                        if canvas_col is not None and c + dc == canvas_col:
                            cap.canvas_value = v
                            cap.source_col_canvas = c + dc + 1
                        elif cap.workpaper_value is None:
                            cap.workpaper_value = v
                            cap.source_col_workpaper = c + dc + 1
                        break
                if canvas_col is not None:
                    cv = _get_cell(rows, r, canvas_col)
                    if cv and _is_probable_value(cv):
                        cap.canvas_value = cv
                        cap.source_col_canvas = canvas_col + 1

    labels_display = {"pm": "计划重要性 (PM)", "te": "可容忍误差 (TE)", "sad": "名义金额 (SAD)"}
    for key, cap in found.items():
        cap.label = labels_display.get(key, cap.label)
    return list(found.values())


def _header_col_index(header_cells: list[str | None], hints: tuple[str, ...]) -> int | None:
    for c, text in enumerate(header_cells):
        if not text:
            continue
        n = _norm(text)
        if any(_norm(h) in n or n in _norm(h) for h in hints):
            return c
    return None


def _extract_cra_table(rows: list[tuple[Any, ...]]) -> list[CraAssertionRow]:
    header_row_idx: int | None = None
    col_assertion = col_cra = col_tt = None

    for r, row in enumerate(rows[:60]):
        cells = [_cell_str(v) for v in row]
        if not any(cells):
            continue
        ca = _header_col_index(cells, _ASSERTION_HEADER_HINTS)
        cc = _header_col_index(cells, _CRA_HEADER_HINTS)
        ct = _header_col_index(cells, _TT_HEADER_HINTS)
        hits = sum(x is not None for x in (ca, cc, ct))
        if hits >= 2 and ca is not None:
            header_row_idx = r
            col_assertion, col_cra, col_tt = ca, cc, ct
            break

    if header_row_idx is None:
        return []

    results: list[CraAssertionRow] = []
    for r in range(header_row_idx + 1, min(header_row_idx + 40, len(rows))):
        assertion = _get_cell(rows, r, col_assertion) if col_assertion is not None else None
        if not assertion or _norm(assertion) in ("合计", "总计", "认定"):
            if results:
                break
            continue
        if len(assertion) > 80:
            continue
        cra = _get_cell(rows, r, col_cra) if col_cra is not None else None
        tt = _get_cell(rows, r, col_tt) if col_tt is not None else None
        if not cra and not tt:
            if results:
                break
            continue
        results.append(
            CraAssertionRow(
                assertion=assertion,
                cra=cra,
                tt=tt,
                source_row=r + 1,
                source_col_assertion=col_assertion + 1 if col_assertion is not None else None,
                source_col_cra=col_cra + 1 if col_cra is not None else None,
                source_col_tt=col_tt + 1 if col_tt is not None else None,
            )
        )
    return results


def parse_lead_sheet_rows(
    rows: list[tuple[Any, ...]],
    *,
    source_file: str = "",
    source_sheet: str = "K.00 Lead Sheet",
) -> LeadSheetDataset:
    materiality = _extract_materiality(rows, source_sheet)
    cra_rows = _extract_cra_table(rows)
    notes: list[str] = []
    if not materiality:
        notes.append("未在 Lead 表摘录到 PM/TE/SAD，请人工打开 K.00 核对。")
    if not cra_rows:
        notes.append("未识别 CRA/TT 认定表，请人工核对各认定 CRA 与 TT。")
    return LeadSheetDataset(
        source_file=source_file,
        source_sheet=source_sheet,
        materiality=materiality,
        cra_rows=cra_rows,
        notes=notes,
    )


def find_lead_sheets(
    path: str | Path,
    *,
    max_rows: int | None = 80,
) -> list[tuple[str, float, list[tuple[Any, ...]]]]:
    path = Path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    found: list[tuple[str, float, list[tuple[Any, ...]]]] = []
    try:
        for ws in wb.worksheets:
            rows = read_worksheet_rows(ws, max_rows=max_rows)
            kind, confidence, *_ = classify_sheet(ws.title, rows)
            name_kind, name_score, _ = score_by_name(ws.title)
            if kind == SheetKind.LEAD:
                found.append((ws.title, confidence, rows))
            elif name_kind == SheetKind.LEAD and name_score >= 0.75:
                found.append((ws.title, name_score, rows))
    finally:
        wb.close()
    found.sort(key=lambda x: x[1], reverse=True)
    return found


def load_lead_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 80,
) -> LeadSheetDataset:
    path = Path(path)
    candidates = find_lead_sheets(path, max_rows=max_rows)

    if sheet_name:
        match = next((c for c in candidates if c[0] == sheet_name), None)
        if match is None:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                ws = wb[sheet_name]
                rows = read_worksheet_rows(ws, max_rows=max_rows)
            finally:
                wb.close()
            return parse_lead_sheet_rows(rows, source_file=str(path), source_sheet=sheet_name)
        name, _, rows = match
        return parse_lead_sheet_rows(rows, source_file=str(path), source_sheet=name)

    if candidates:
        name, _, rows = candidates[0]
        return parse_lead_sheet_rows(rows, source_file=str(path), source_sheet=name)

    return LeadSheetDataset(
        source_file=str(path),
        source_sheet="",
        notes=["未识别 K.00 Lead Sheet 工作表。"],
    )
