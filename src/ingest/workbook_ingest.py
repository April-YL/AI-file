"""整本固定资产底稿接入：结构识别 + 多 sheet 加载 + 勾稽关系。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
    build_addition_execution_path,
    load_addition_sample_output_from_workbook,
    load_addition_test_from_workbook,
)
from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalSampleOutputDataset,
    DisposalTestSheetDataset,
    build_disposal_execution_path,
    load_disposal_sample_output_from_workbook,
    load_disposal_test_from_workbook,
)
from ingest.k03_sheet import K03SheetDataset, load_k03_sheets_from_workbook
from ingest.lead_sheet import LeadSheetDataset, load_lead_from_workbook
from ingest.models import SheetKind
from ingest.reconciliation import ReconciliationCheck, run_workbook_reconciliations
from ingest.records import (
    DisposalListSummary,
    FaListDataset,
    build_disposal_list_summary,
    load_fa_list_from_workbook,
)
from ingest.rollforward_sheet import RollforwardSheetDataset, load_rollforward_from_workbook
from ingest.sheet_loader import load_asset_sheet_from_workbook
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
    addition_test: AdditionTestSheetDataset | None = None
    addition_sample_output: AdditionSampleOutputDataset | None = None
    addition_execution_path: AdditionExecutionPathDataset | None = None
    disposal_list: FaListDataset | None = None
    disposal_list_summary: DisposalListSummary | None = None
    disposal_lists: list[FaListDataset] = field(default_factory=list)
    disposal_test: DisposalTestSheetDataset | None = None
    disposal_sample_output: DisposalSampleOutputDataset | None = None
    disposal_execution_path: DisposalExecutionPathDataset | None = None
    k03_sheets: list[K03SheetDataset] = field(default_factory=list)
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
            "addition_test": _addition_test_summary(self.addition_test),
            "addition_sample_output": _addition_sample_output_summary(
                self.addition_sample_output
            ),
            "addition_execution_path": (
                self.addition_execution_path.to_dict()
                if self.addition_execution_path
                else None
            ),
            "disposal_list": _dataset_summary(self.disposal_list),
            "disposal_list_summary": _disposal_list_summary(self.disposal_list_summary),
            "disposal_test": _disposal_test_summary(self.disposal_test),
            "disposal_sample_output": _disposal_sample_output_summary(
                self.disposal_sample_output
            ),
            "disposal_execution_path": (
                self.disposal_execution_path.to_dict()
                if self.disposal_execution_path
                else None
            ),
            "k03_sheets": [sheet.to_dict() for sheet in self.k03_sheets],
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


def _disposal_list_summary(ds: DisposalListSummary | None) -> dict[str, Any] | None:
    if ds is None or not ds.source_sheet:
        return None
    return ds.to_dict()


def _addition_test_summary(
    ds: AdditionTestSheetDataset | None,
) -> dict[str, Any] | None:
    if ds is None or not ds.source_sheet:
        return None
    return {
        "source_sheet": ds.source_sheet,
        "waiver_note_text": ds.waiver_note_text,
        "waiver_note_rows": ds.waiver_note_rows,
        "amounts": {k: v.to_dict() for k, v in ds.amounts.items()},
        "tested_samples": [row.to_dict() for row in ds.tested_samples],
        "module_assessments": [m.to_dict() for m in ds.module_assessments],
        "recognition_confidence": ds.recognition_confidence,
        "notes": ds.notes,
    }


def _addition_sample_output_summary(
    ds: AdditionSampleOutputDataset | None,
) -> dict[str, Any] | None:
    if ds is None or not ds.source_sheet:
        return None
    return {
        "source_sheet": ds.source_sheet,
        "amounts": {k: v.to_dict() for k, v in ds.amounts.items()},
        "selected_samples": [row.to_dict() for row in ds.selected_samples],
        "module_assessments": [m.to_dict() for m in ds.module_assessments],
        "recognition_confidence": ds.recognition_confidence,
        "notes": ds.notes,
    }


def _disposal_test_summary(
    ds: DisposalTestSheetDataset | None,
) -> dict[str, Any] | None:
    if ds is None or not ds.source_sheet:
        return None
    return {
        "source_sheet": ds.source_sheet,
        "waiver_note_text": ds.waiver_note_text,
        "waiver_note_rows": ds.waiver_note_rows,
        "amounts": {k: v.to_dict() for k, v in ds.amounts.items()},
        "reconciliation_matrix": (
            ds.reconciliation_matrix.to_dict() if ds.reconciliation_matrix else None
        ),
        "tested_samples": [row.to_dict() for row in ds.tested_samples],
        "module_assessments": [m.to_dict() for m in ds.module_assessments],
        "recognition_confidence": ds.recognition_confidence,
        "usable_for_rules": ds.usable_for_rules,
        "notes": ds.notes,
    }


def _disposal_sample_output_summary(
    ds: DisposalSampleOutputDataset | None,
) -> dict[str, Any] | None:
    if ds is None or not ds.source_sheet:
        return None
    return {
        "source_sheet": ds.source_sheet,
        "parameters": {k: v.to_dict() for k, v in ds.parameters.items()},
        "amounts": {k: v.to_dict() for k, v in ds.amounts.items()},
        "selected_samples": [row.to_dict() for row in ds.selected_samples],
        "module_assessments": [m.to_dict() for m in ds.module_assessments],
        "recognition_confidence": ds.recognition_confidence,
        "usable_for_rules": ds.usable_for_rules,
        "notes": ds.notes,
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
        "layout_profile": rf.layout_profile.value,
        "has_movement_rows": rf.has_movement_rows,
        "section_presence": rf.section_presence,
        "section_evidence": rf.section_evidence,
        "section_regions": {
            sid: {
                "anchor_row": reg.anchor_row,
                "start_row": reg.start_row,
                "end_row": reg.end_row,
                "evidence": reg.evidence,
            }
            for sid, reg in rf.section_regions.items()
        },
        "section_conflicts": rf.section_conflicts,
        "recognition_confidence": rf.recognition_confidence,
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
        "block_count": len(lead.blocks),
        "blocks": [
            {
                "kind": b.kind.value,
                "anchor_row": b.anchor_row,
                "start_row": b.start_row,
                "end_row": b.end_row,
                "confidence": b.confidence,
            }
            for b in lead.blocks
        ],
        "basic_info_fields": len(lead.basic_info_fields),
        "materiality_items": len(lead.materiality),
        "cra_rows": len(lead.cra_rows),
        "expectation_rows": len(lead.expectations),
        "movement_rows": len(lead.movement_rows),
        "adjustment_rows": len(lead.adjustment_rows),
        "layout_variant": lead.layout_variant,
        "volatility_amount_source": (
            lead.volatility.amount_source if lead.volatility else None
        ),
        "notes": lead.notes,
    }


def _candidate_sheet_names(structure: WorkbookStructure, kind: SheetKind) -> list[str]:
    sheets = sorted(
        structure.sheets_by_kind.get(kind.value, []),
        key=lambda s: s.confidence,
        reverse=True,
    )
    return [s.sheet_name for s in sheets]


def _first_sheet_name(
    structure: WorkbookStructure,
    kind: SheetKind,
    explicit_name: str | None = None,
) -> str | None:
    if explicit_name:
        return explicit_name
    names = _candidate_sheet_names(structure, kind)
    return names[0] if names else None


def _load_fa_list_candidate_sheets(
    path: Path,
    structure: WorkbookStructure,
    *,
    max_rows: int | None,
) -> list[FaListDataset]:
    datasets: list[FaListDataset] = []
    for name in _candidate_sheet_names(structure, SheetKind.FA_LIST):
        dataset = load_fa_list_from_workbook(path, sheet_name=name, max_rows=max_rows)
        if dataset.records or dataset.mapped_fields:
            datasets.append(dataset)
    return datasets


def _load_asset_candidate_sheets(
    path: Path,
    structure: WorkbookStructure,
    kind: SheetKind,
    *,
    max_rows: int | None,
) -> list[FaListDataset]:
    datasets: list[FaListDataset] = []
    for name in _candidate_sheet_names(structure, kind):
        dataset = load_asset_sheet_from_workbook(
            path,
            kind,
            sheet_name=name,
            max_rows=max_rows,
        )
        if dataset.records or dataset.mapped_fields:
            datasets.append(dataset)
    return datasets


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

    fa_sheet = _first_sheet_name(structure, SheetKind.FA_LIST, fa_sheet)
    summary_sheet = _first_sheet_name(structure, SheetKind.SUMMARY, summary_sheet)
    lead_sheet = _first_sheet_name(structure, SheetKind.LEAD, lead_sheet)
    rollforward_sheet = _first_sheet_name(
        structure, SheetKind.ROLLFORWARD, rollforward_sheet
    )
    addition_sheet = _first_sheet_name(structure, SheetKind.ADDITION_LIST, addition_sheet)
    addition_test_sheet = _first_sheet_name(structure, SheetKind.ADDITION_TEST)
    addition_sample_output_sheet = _first_sheet_name(
        structure, SheetKind.ADDITION_SAMPLE_OUTPUT
    )
    disposal_sheet = _first_sheet_name(structure, SheetKind.DISPOSAL_LIST, disposal_sheet)
    disposal_test_sheet = _first_sheet_name(structure, SheetKind.DISPOSAL_TEST)
    disposal_sample_output_sheet = _first_sheet_name(
        structure, SheetKind.DISPOSAL_SAMPLE_OUTPUT
    )

    # Lists feed population-level rules and must never be truncated by the
    # workpaper-module parsing budget.
    fa_list = load_fa_list_from_workbook(path, sheet_name=fa_sheet, max_rows=None)
    if not fa_list.records and not fa_list.mapped_fields:
        fa_list = None

    fa_list_sheets = (
        [fa_list]
        if fa_list is not None
        else _load_fa_list_candidate_sheets(path, structure, max_rows=None)
    )

    rollforward = load_rollforward_from_workbook(
        path,
        sheet_name=rollforward_sheet,
        max_rows=max_rows,
    )
    if not rollforward.source_sheet:
        rollforward = None

    addition_list = (
        load_asset_sheet_from_workbook(
            path,
            SheetKind.ADDITION_LIST,
            sheet_name=addition_sheet,
            max_rows=None,
        )
        if addition_sheet
        else None
    )
    if addition_list and not addition_list.records and not addition_list.mapped_fields:
        addition_list = None
    addition_lists = (
        [addition_list]
        if addition_list is not None
        else _load_asset_candidate_sheets(
            path,
            structure,
            SheetKind.ADDITION_LIST,
            max_rows=None,
        )
    )

    addition_test = (
        load_addition_test_from_workbook(
            path,
            sheet_name=addition_test_sheet,
            max_rows=max_rows,
        )
        if addition_test_sheet
        else None
    )
    addition_sample_output = (
        load_addition_sample_output_from_workbook(
            path,
            sheet_name=addition_sample_output_sheet,
            max_rows=max_rows,
        )
        if addition_sample_output_sheet
        else None
    )

    disposal_list = (
        load_asset_sheet_from_workbook(
            path,
            SheetKind.DISPOSAL_LIST,
            sheet_name=disposal_sheet,
            max_rows=None,
        )
        if disposal_sheet
        else None
    )
    if disposal_list and not disposal_list.records and not disposal_list.mapped_fields:
        disposal_list = None
    disposal_lists = (
        [disposal_list]
        if disposal_list is not None
        else _load_asset_candidate_sheets(
            path,
            structure,
            SheetKind.DISPOSAL_LIST,
            max_rows=None,
        )
    )
    disposal_list_summary = build_disposal_list_summary(disposal_list)
    disposal_test = (
        load_disposal_test_from_workbook(
            path,
            sheet_name=disposal_test_sheet,
            max_rows=max_rows,
        )
        if disposal_test_sheet
        else None
    )
    disposal_sample_output = (
        load_disposal_sample_output_from_workbook(
            path,
            sheet_name=disposal_sample_output_sheet,
            max_rows=max_rows,
        )
        if disposal_sample_output_sheet
        else None
    )
    k03_sheets = load_k03_sheets_from_workbook(path, max_rows=None)

    summary = load_summary_from_workbook(path, sheet_name=summary_sheet)
    if not summary.programs and not summary.header_row:
        summary = None

    lead = load_lead_from_workbook(path, sheet_name=lead_sheet)
    if (
        not lead.source_sheet
        and not lead.blocks
        and not lead.materiality
        and not lead.cra_rows
    ):
        lead = None

    reconciliations = run_workbook_reconciliations(
        fa_list=fa_list,
        rollforward=rollforward,
        addition_list=addition_list,
        disposal_list=disposal_list,
    )

    addition_execution_path = build_addition_execution_path(
        summary=summary,
        addition_list=addition_list,
        addition_test=addition_test,
        addition_sample_output=addition_sample_output,
    )
    disposal_execution_path = build_disposal_execution_path(
        summary=summary,
        disposal_list=disposal_list,
        disposal_test=disposal_test,
        disposal_sample_output=disposal_sample_output,
    )

    return WorkbookIngestContext(
        source_file=str(path),
        structure=structure,
        fa_list=fa_list,
        fa_list_sheets=fa_list_sheets,
        rollforward=rollforward,
        addition_list=addition_list,
        addition_lists=addition_lists,
        addition_test=addition_test,
        addition_sample_output=addition_sample_output,
        addition_execution_path=addition_execution_path,
        disposal_list=disposal_list,
        disposal_list_summary=disposal_list_summary,
        disposal_lists=disposal_lists,
        disposal_test=disposal_test,
        disposal_sample_output=disposal_sample_output,
        disposal_execution_path=disposal_execution_path,
        k03_sheets=k03_sheets,
        summary=summary,
        lead=lead,
        reconciliations=reconciliations,
    )
