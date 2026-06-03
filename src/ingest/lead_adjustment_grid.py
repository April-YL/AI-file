"""K.00 调整汇总表区域 grid 摘录，供 LLM 版式识别与行抽取。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl

from ingest.lead_sheet import LeadSheetDataset
from ingest.lead_sheet_blocks import LeadBlockKind, block_for_kind, slice_rows_for_block
from ingest.workbook_reader import read_worksheet_rows

_DEFAULT_MAX_ROWS = 200
_DEFAULT_MAX_COL = 14
_DEFAULT_MAX_GRID_ROWS = 35


def _cell_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def build_adjustment_grid(
    rows: list[tuple[Any, ...]],
    lead: LeadSheetDataset,
    *,
    max_grid_rows: int = _DEFAULT_MAX_GRID_ROWS,
    max_col: int = _DEFAULT_MAX_COL,
) -> dict[str, Any] | None:
    """
    截取调整汇总块为二维字符串 grid（1-based 行号写入元数据）。

    无 adjustment 块时返回 None。
    """
    block = lead.block(LeadBlockKind.ADJUSTMENT_SUMMARY)
    if block is None:
        return None

    scope = slice_rows_for_block(rows, block)
    grid: list[list[str | None]] = []
    for row in scope[:max_grid_rows]:
        cells = [_cell_str(v) for v in row[:max_col]]
        if any(cells):
            grid.append(cells)

    return {
        "anchor_row": block.anchor_row,
        "start_row": block.start_row,
        "end_row": block.end_row,
        "anchor_text": block.anchor_text,
        "confidence": block.confidence,
        "grid": grid,
        "grid_row_count": len(grid),
    }


def load_adjustment_grid_for_lead(
    workbook_path: str | Path,
    lead: LeadSheetDataset,
    *,
    max_rows: int = _DEFAULT_MAX_ROWS,
) -> dict[str, Any] | None:
    """从工作簿重读 Lead 表并生成 adjustment_grid（与 parse 行数上限一致）。"""
    path = Path(workbook_path)
    if path.suffix.lower() not in (".xlsx", ".xlsm", ".xlsb"):
        return None
    if not lead.source_sheet:
        return None

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if lead.source_sheet not in wb.sheetnames:
            return None
        ws = wb[lead.source_sheet]
        rows = read_worksheet_rows(ws, max_rows=max_rows, max_col=100)
    finally:
        wb.close()

    return build_adjustment_grid(rows, lead)
