from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingest.records import FaListDataset, load_fa_list_from_workbook
from ingest.summary_sheet import SummarySheetDataset, load_summary_from_workbook


@dataclass
class WorkbookQcContext:
    """整本底稿质检上下文（当前：FA list + 汇总页）。"""

    source_file: str
    fa_list: FaListDataset | None
    summary: SummarySheetDataset | None


def load_workbook_context(
    path: str | Path,
    *,
    fa_sheet: str | None = None,
    summary_sheet: str | None = None,
) -> WorkbookQcContext:
    path = Path(path)
    fa = load_fa_list_from_workbook(path, sheet_name=fa_sheet)
    summary = load_summary_from_workbook(path, sheet_name=summary_sheet)
    if not fa.records:
        fa = None
    if not summary.programs and not summary.header_row:
        summary = None
    return WorkbookQcContext(
        source_file=str(path),
        fa_list=fa,
        summary=summary,
    )
