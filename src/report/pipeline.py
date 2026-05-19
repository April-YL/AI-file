from __future__ import annotations

from ingest.records import FaListDataset
from ingest.workbook_context import WorkbookQcContext, load_workbook_context
from llm.config import load_llm_config
from llm.review import enrich_report_with_llm
from report.summary import QcReport, build_report
from rules.models import ColumnContext
from rules.psp_completion import check_psp_completion
from rules.registry import attach_rule_metadata
from rules.runner import FA_LIST_RULE_IDS, run_fa_list_rules

WORKBOOK_RULE_IDS = (*FA_LIST_RULE_IDS, "psp_completion")


def run_workbook_qc(
    ctx: WorkbookQcContext,
    *,
    llm: bool | None = None,
) -> QcReport:
    issues = []
    records = []
    rule_ids: list[str] = []
    source_sheet = ""

    if ctx.fa_list:
        fa_ctx = ColumnContext(
            mapped_fields={m.standard_field for m in ctx.fa_list.mapped_fields},
            source_sheet=ctx.fa_list.source_sheet,
            procedure_code="FA_LIST",
        )
        issues.extend(run_fa_list_rules(ctx.fa_list.records, fa_ctx))
        records = ctx.fa_list.records
        rule_ids.extend(FA_LIST_RULE_IDS)
        source_sheet = ctx.fa_list.source_sheet

    if ctx.summary:
        issues.extend(attach_rule_metadata(check_psp_completion(ctx.summary)))
        rule_ids.append("psp_completion")
        if not source_sheet:
            source_sheet = ctx.summary.source_sheet

    if not rule_ids:
        rule_ids = list(WORKBOOK_RULE_IDS)

    report = build_report(
        source_file=ctx.source_file,
        source_sheet=source_sheet or "workbook",
        procedure_code="WORKBOOK",
        rule_ids=list(dict.fromkeys(rule_ids)),
        records=records,
        issues=issues,
    )
    config = load_llm_config(cli_enabled=llm)
    if config.enabled:
        report = enrich_report_with_llm(
            report,
            config,
            summary=ctx.summary,
        )
    return report


def run_workbook_qc_from_path(
    path: str,
    *,
    fa_sheet: str | None = None,
    summary_sheet: str | None = None,
    llm: bool | None = None,
) -> QcReport:
    ctx = load_workbook_context(path, fa_sheet=fa_sheet, summary_sheet=summary_sheet)
    return run_workbook_qc(ctx, llm=llm)


def run_input_qc(
    path: str,
    *,
    fa_sheet: str | None = None,
    summary_sheet: str | None = None,
    llm: bool | None = None,
) -> QcReport:
    """CSV 仅 FA list；Excel 走整本 workbook 流水线。"""
    from pathlib import Path

    from report.export_json import run_fa_list_qc
    from ingest.records import load_fa_list_csv

    p = Path(path)
    if p.suffix.lower() == ".csv":
        return run_fa_list_qc(load_fa_list_csv(p), llm=llm)
    return run_workbook_qc_from_path(
        str(p),
        fa_sheet=fa_sheet,
        summary_sheet=summary_sheet,
        llm=llm,
    )
