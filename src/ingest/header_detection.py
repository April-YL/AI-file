from __future__ import annotations

from typing import Any

from ingest.constants import CONTENT_SIGNATURES
from ingest.field_mapping import map_headers, match_standard_field
from ingest.models import SheetKind

_PROSE_ROW_PREFIXES = ("获取", "编制", "说明", "注：", "注:", "按照", "根据", "索引")
_PROSE_MIN_LEN = 60


def _row_looks_like_prose(cells: list[tuple[int, str]]) -> bool:
    """跳过 SOP 说明整段文字误当表头（处置清单等）。"""
    if not cells:
        return False
    if any(len(text) > _PROSE_MIN_LEN for _, text in cells):
        return True
    joined = "".join(text for _, text in cells)
    if len(joined) > 120 and len(cells) <= 2:
        return True
    for _, text in cells:
        if len(text) >= 8 and text.startswith(_PROSE_ROW_PREFIXES):
            return True
    return False


def _header_row_score(
    mapped_count: int,
    header_cells: list[tuple[int, str]],
    sheet_kind: SheetKind | None,
) -> int:
    if sheet_kind is None:
        return mapped_count
    if sheet_kind == SheetKind.DISPOSAL_LIST:
        present = {
            f
            for _, text in header_cells
            if (f := match_standard_field(text, sheet_kind))
        }
        sig = CONTENT_SIGNATURES.get(SheetKind.DISPOSAL_LIST, set())
        hit = len(present & sig)
        score = hit * 10 + mapped_count
        if "disposal_date" in present or "disposal_method" in present:
            score += 5
        return score
    return mapped_count


def scan_rows_for_headers(
    rows: list[tuple[Any, ...]],
    max_rows: int = 100,
    max_cols: int = 100,
    sheet_kind: SheetKind | None = None,
) -> tuple[int | None, list[tuple[int, str]], list[str]]:
    """
    在前 N 行中找表头候选行。
    返回 (header_row_1based, header_cells, unmapped).
    """
    best_row: int | None = None
    best_score = 0
    best_cells: list[tuple[int, str]] = []
    best_unmapped: list[str] = []

    limit = min(len(rows), max_rows)
    for r_idx in range(limit):
        row = rows[r_idx]
        if row is None:
            continue
        cells: list[tuple[int, str]] = []
        for c_idx, val in enumerate(row[:max_cols], start=1):
            if val is None or not str(val).strip():
                continue
            cells.append((c_idx, str(val).strip()))
        if not cells or _row_looks_like_prose(cells):
            continue
        mapped, unmapped = map_headers(cells, sheet_kind)
        row_score = _header_row_score(len(mapped), cells, sheet_kind)
        if row_score > best_score:
            best_score = row_score
            best_row = r_idx + 1
            best_cells = cells
            best_unmapped = unmapped

    if best_row is None:
        return None, [], []
    _, unmapped = map_headers(best_cells, sheet_kind)
    return best_row, best_cells, unmapped


def count_signature_fields(
    header_cells: list[tuple[int, str]],
    signature: set[str],
    sheet_kind: SheetKind | None = None,
) -> int:
    present = set()
    for _, text in header_cells:
        f = match_standard_field(text, sheet_kind)
        if f:
            present.add(f)
    return len(signature & present)
