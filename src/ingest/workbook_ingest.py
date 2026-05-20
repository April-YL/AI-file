"""整本固定资产底稿接入：结构识别 + 多 sheet 加载 + 勾稽关系。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ingest.lead_sheet import LeadSheetDataset, load_lead_from_workbook
from ingest.models import SheetKind
from ingest.reconciliation import ReconciliationCheck, run_workbook_reconciliations
from ingest.records import FaListDataset, load_fa_list_from_workbook
from ingest.rollforward_sheet import RollforwardSheetDataset, load_rollforward_from_workbook
from ingest.sheet_loader import load_all_sheets_of_kind, load_asset_sheet_from_workbook
from ingest.summary_sheet import SummarySheetDataset, load_summary_from_workbook
from ingest.workbook_structure import WorkbookStructure, analyze_workbook_structure


@dataclass
class WorkbookIngestContext:
    """整本底稿结构化读取结果（ingest 层，不含 rules findings）。"""

    source_file: str
    structure: WorkbookStructure
    fa_list: FaListDataset | None = None
    fa_list_sheets: list[FaListDataset] = field(default_factory=list)
    rollforward: RollforwardSheetDataset | None = None
    addition_list: FaListDataset | None = None
    addition_lists: list[FaListDataset] = field(default_factory=list)
    disposal_list: FaListDataset | None = None
    disposal_lists: list[FaListDataset] = field(default_factory=list)
    summary: SummarySheetDataset | None = None
    lead: LeadSheetDataset | None = None
    reconciliations: list[ReconciliationCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "structure": self.structure.to_dict(),
            "fa_list": _dataset_summary(self.fa_list),
            "fa_list_sheets": [_dataset_summary(d) for d in self.fa_list_sheets],
            "rollforward": _rollforward_summary(self.rollforward),
            "addition_list": _dataset_summary(self.addition_list),
            "disposal_list": _dataset_summary(self.disposal_list),
            "summary": _summary_summary(self.summary),
            "lead": _lead_summary(self.lead),
            "reconciliations": [c.to_dict() for c in self.reconciliations],
        }


def _dataset_summary(ds: FaListDataset | None) -> dict[str, Any] | None:
    if ds is None or not ds.source_sheet:
        return None
    return {
        "source_sheet": ds.source_sheet,
        "record_count": len(ds.records),
        "mapped_fields": [m.standard_field for m in ds.mapped_fields],
    }


def _rollforward_summary(rf: RollforwardSheetDataset | None) -> dict[str, Any] | None:
    if rf is None or not rf.source_sheet:
        return None
    return {
        "source_sheet": rf.source_sheet,
        "header_row": rf.header_row,
        "total_row": rf.total_row,
        "amount_column_bindings": [
            {
                "measure": b.measure,
                "period_role": b.period_role.value,
                "column_index": b.column_index,
                "source_header": b.source_header,
            }
            for b in rf.amount_column_bindings
        ],
        "opening_totals": {k: str(v) for k, v in rf.opening_totals.items() if v is not None},
        "ending_totals": {k: str(v) for k, v in rf.ending_totals.items() if v is not None},
        "notes": rf.notes,
    }


def _summary_summary(summary: SummarySheetDataset | None) -> dict[str, Any] | None:
    if summary is None or not summary.source_sheet:
        return None
    return {
        "source_sheet": summary.source_sheet,
        "header_row": summary.header_row,
        "layout": summary.layout,
        "last_data_row": summary.last_data_row,
        "program_count": len(summary.programs),
        "column_bindings": [
            {"role": b.role, "source_header": b.source_header, "column_index": b.column_index}
            for b in summary.column_bindings
        ],
        "notes": summary.notes,
    }


def _lead_summary(lead: LeadSheetDataset | None) -> dict[str, Any] | None:
    if lead is None or not lead.source_sheet:
        return None
    return {
        "source_sheet": lead.source_sheet,
        "materiality_items": len(lead.materiality),
        "cra_rows": len(lead.cra_rows),
    }


def load_workbook_ingest(
    path: str | Path,
    *,
    fa_sheet: str | None = None,
    summary_sheet: str | None = None,
    lead_sheet: str | None = None,
    rollforward_sheet: str | None = None,
    addition_sheet: str | None = None,
    disposal_sheet: str | None = None,
    max_rows: int = 150,
) -> WorkbookIngestContext:
    path = Path(path)
    structure = analyze_workbook_structure(path, max_rows=max_rows)

    fa_list = load_fa_list_from_workbook(path, sheet_name=fa_sheet, max_rows=max_rows)
    if not fa_list.records and not fa_list.mapped_fields:
        fa_list = None

    fa_list_sheets = load_all_sheets_of_kind(path, SheetKind.FA_LIST, max_rows=max_rows)

    rollforward = load_rollforward_from_workbook(
        path,
        sheet_name=rollforward_sheet,
        max_rows=max_rows,
    )
    if not rollforward.source_sheet:
        rollforward = None

    addition_list = load_asset_sheet_from_workbook(
        path,
        SheetKind.ADDITION_LIST,
        sheet_name=addition_sheet,
        max_rows=max_rows,
    )
    if not addition_list.records and not addition_list.mapped_fields:
        addition_list = None
    addition_lists = load_all_sheets_of_kind(path, SheetKind.ADDITION_LIST, max_rows=max_rows)

    disposal_list = load_asset_sheet_from_workbook(
        path,
        SheetKind.DISPOSAL_LIST,
        sheet_name=disposal_sheet,
        max_rows=max_rows,
    )
    if not disposal_list.records and not disposal_list.mapped_fields:
        disposal_list = None
    disposal_lists = load_all_sheets_of_kind(path, SheetKind.DISPOSAL_LIST, max_rows=max_rows)

    summary = load_summary_from_workbook(path, sheet_name=summary_sheet)
    if not summary.programs and not summary.header_row:
        summary = None

    lead = load_lead_from_workbook(path, sheet_name=lead_sheet)
    if not lead.source_sheet and not lead.materiality and not lead.cra_rows:
        lead = None

    reconciliations = run_workbook_reconciliations(
        fa_list=fa_list,
        rollforward=rollforward,
        addition_list=addition_list,
        disposal_list=disposal_list,
    )

    return WorkbookIngestContext(
        source_file=str(path),
        structure=structure,
        fa_list=fa_list,
        fa_list_sheets=fa_list_sheets,
        rollforward=rollforward,
        addition_list=addition_list,
        addition_lists=addition_lists,
        disposal_list=disposal_list,
        disposal_lists=disposal_lists,
        summary=summary,
        lead=lead,
        reconciliations=reconciliations,
    )
