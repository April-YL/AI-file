from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
)
from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalSampleOutputDataset,
    DisposalTestSheetDataset,
)
from ingest.k03_sheet import K03SheetDataset
from ingest.lead_sheet import LeadSheetDataset
from ingest.reconciliation import ReconciliationCheck
from ingest.records import DisposalListSummary, FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from ingest.summary_sheet import SummarySheetDataset
from ingest.workbook_ingest import load_workbook_ingest
from ingest.workbook_structure import WorkbookStructure


@dataclass
class WorkbookQcContext:
    """整本底稿质检上下文（规则引擎 + LLM 共用）。"""

    source_file: str
    fa_list: FaListDataset | None
    summary: SummarySheetDataset | None
    lead: LeadSheetDataset | None
    rollforward: RollforwardSheetDataset | None = None
    addition_list: FaListDataset | None = None
    addition_test: AdditionTestSheetDataset | None = None
    addition_sample_output: AdditionSampleOutputDataset | None = None
    addition_execution_path: AdditionExecutionPathDataset | None = None
    disposal_list: FaListDataset | None = None
    disposal_list_summary: DisposalListSummary | None = None
    disposal_test: DisposalTestSheetDataset | None = None
    disposal_sample_output: DisposalSampleOutputDataset | None = None
    disposal_execution_path: DisposalExecutionPathDataset | None = None
    k03_sheets: list[K03SheetDataset] = field(default_factory=list)
    structure: WorkbookStructure | None = None
    reconciliations: list[ReconciliationCheck] = field(default_factory=list)


def load_workbook_context(
    path: str | Path,
    *,
    fa_sheet: str | None = None,
    summary_sheet: str | None = None,
    lead_sheet: str | None = None,
    rollforward_sheet: str | None = None,
    addition_sheet: str | None = None,
    disposal_sheet: str | None = None,
    max_rows: int = 200,
) -> WorkbookQcContext:
    """加载整本底稿核心 sheet（与 ``load_workbook_ingest`` 对齐，供 QC 与 LLM 使用）。"""
    ing = load_workbook_ingest(
        path,
        fa_sheet=fa_sheet,
        summary_sheet=summary_sheet,
        lead_sheet=lead_sheet,
        rollforward_sheet=rollforward_sheet,
        addition_sheet=addition_sheet,
        disposal_sheet=disposal_sheet,
        max_rows=max_rows,
    )
    return WorkbookQcContext(
        source_file=ing.source_file,
        fa_list=ing.fa_list,
        summary=ing.summary,
        lead=ing.lead,
        rollforward=ing.rollforward,
        addition_list=ing.addition_list,
        addition_test=ing.addition_test,
        addition_sample_output=ing.addition_sample_output,
        addition_execution_path=ing.addition_execution_path,
        disposal_list=ing.disposal_list,
        disposal_list_summary=ing.disposal_list_summary,
        disposal_test=ing.disposal_test,
        disposal_sample_output=ing.disposal_sample_output,
        disposal_execution_path=ing.disposal_execution_path,
        k03_sheets=list(ing.k03_sheets),
        structure=ing.structure,
        reconciliations=list(ing.reconciliations),
    )
