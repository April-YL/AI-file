from __future__ import annotations

from pathlib import Path

from ingest.workbook_context import WorkbookQcContext, load_workbook_context
from ingest.workbook_reader import list_workbook_sheet_titles
from llm.config import load_llm_config
from llm.review import enrich_report_with_llm
from report.manual_review import build_manual_review_sections
from report.summary import QcReport, build_report
from report.lead_sheet_report import build_lead_sheet_section
from report.rollforward_sheet_report import build_rollforward_sheet_section
from report.summary_sheet_report import build_summary_sheet_section
from rules.lead_runner import LEAD_RULE_IDS, run_lead_rules
from rules.models import ColumnContext
from rules.psp_completion import check_psp_completion
from rules.registry import attach_rule_metadata
from rules.rollforward_runner import ROLLFORWARD_RULE_IDS, run_rollforward_rules
from rules.runner import FA_LIST_RULE_IDS, run_fa_list_rules

WORKBOOK_RULE_IDS = (
    *FA_LIST_RULE_IDS,
    "psp_completion",
    *LEAD_RULE_IDS,
    *ROLLFORWARD_RULE_IDS,
)


def run_workbook_qc(
    ctx: WorkbookQcContext,
    *,
    llm: bool | None = None,
) -> QcReport:
    config = load_llm_config(cli_enabled=llm)
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
        sheet_titles: list[str] | None = None
        wb_for_psp: str | None = None
        if Path(ctx.source_file).suffix.lower() in (".xlsx", ".xlsm", ".xlsb"):
            wb_for_psp = ctx.source_file
            try:
                sheet_titles = list_workbook_sheet_titles(ctx.source_file)
            except Exception:
                sheet_titles = None
                wb_for_psp = None
        waiver_reason_reviewer = None
        if config.enabled:
            from llm.summary_psp_review import (
                build_waiver_semantic_context,
                review_waiver_reason_with_llm,
            )

            waiver_semantic_context = build_waiver_semantic_context(
                lead=ctx.lead,
                rollforward=ctx.rollforward,
                addition_list=ctx.addition_list,
                disposal_list=ctx.disposal_list,
                reconciliations=ctx.reconciliations,
                workbook_sheet_titles=sheet_titles,
            )

            def waiver_reason_reviewer(row):
                return review_waiver_reason_with_llm(
                    row,
                    config,
                    semantic_context=waiver_semantic_context,
                )

        psp_raw_issues = check_psp_completion(
            ctx.summary,
            workbook_sheet_titles=sheet_titles,
            workbook_path=wb_for_psp,
            waiver_reason_reviewer=waiver_reason_reviewer,
            enforce_template_completeness=True,
        )
        if config.enabled and wb_for_psp and sheet_titles:
            from llm.summary_psp_review import build_sheet_semantic_issues

            psp_raw_issues.extend(
                build_sheet_semantic_issues(
                    ctx.summary,
                    config,
                    workbook_path=wb_for_psp,
                    workbook_sheet_titles=sheet_titles,
                )
            )
        psp_issues = attach_rule_metadata(psp_raw_issues)
        issues.extend(psp_issues)
        summary_sheet_section = build_summary_sheet_section(ctx.summary, psp_issues)
        rule_ids.append("psp_completion")
        if not source_sheet:
            source_sheet = ctx.summary.source_sheet
    else:
        summary_sheet_section = None

    lead_sheet_section = None
    if ctx.lead:
        lead_raw_issues = run_lead_rules(ctx.lead, rollforward=ctx.rollforward)
        if config.enabled:
            from llm.lead_review import (
                RULE_EXPECTATION,
                RULE_FLUCTUATION,
                build_lead_semantic_issues,
            )

            llm_lead_issues = build_lead_semantic_issues(ctx.lead, config)
            lead_raw_issues.extend(llm_lead_issues)
            if llm_lead_issues:
                for rid in (RULE_EXPECTATION, RULE_FLUCTUATION):
                    if rid not in rule_ids:
                        rule_ids.append(rid)
        lead_issues = attach_rule_metadata(lead_raw_issues)
        issues.extend(lead_issues)
        lead_sheet_section = build_lead_sheet_section(ctx.lead, lead_issues)
        rule_ids.extend(list(LEAD_RULE_IDS))
        if not source_sheet:
            source_sheet = ctx.lead.source_sheet

    rollforward_sheet_section = None
    if ctx.rollforward:
        rollforward_issues = attach_rule_metadata(
            run_rollforward_rules(
                ctx.rollforward,
                lead=ctx.lead,
                reconciliations=ctx.reconciliations,
            )
        )
        issues.extend(rollforward_issues)
        rollforward_sheet_section = build_rollforward_sheet_section(
            ctx.rollforward, rollforward_issues
        )
        rule_ids.extend(list(ROLLFORWARD_RULE_IDS))
        if not source_sheet:
            source_sheet = ctx.rollforward.source_sheet

    if not rule_ids:
        rule_ids = list(WORKBOOK_RULE_IDS)

    report = build_report(
        source_file=ctx.source_file,
        source_sheet=source_sheet or "workbook",
        procedure_code="WORKBOOK",
        rule_ids=list(dict.fromkeys(rule_ids)),
        records=records,
        issues=issues,
        summary_sheet_section=summary_sheet_section,
        lead_sheet_section=lead_sheet_section,
        rollforward_sheet_section=rollforward_sheet_section,
    )
    report.manual_review_sections = build_manual_review_sections(ctx.lead)

    if config.enabled:
        report = enrich_report_with_llm(
            report,
            config,
            summary=ctx.summary,
            workbook=ctx,
        )
    return report


def run_workbook_qc_from_path(
    path: str,
    *,
    fa_sheet: str | None = None,
    summary_sheet: str | None = None,
    lead_sheet: str | None = None,
    rollforward_sheet: str | None = None,
    addition_sheet: str | None = None,
    disposal_sheet: str | None = None,
    llm: bool | None = None,
) -> QcReport:
    ctx = load_workbook_context(
        path,
        fa_sheet=fa_sheet,
        summary_sheet=summary_sheet,
        lead_sheet=lead_sheet,
        rollforward_sheet=rollforward_sheet,
        addition_sheet=addition_sheet,
        disposal_sheet=disposal_sheet,
    )
    return run_workbook_qc(ctx, llm=llm)


def run_input_qc(
    path: str,
    *,
    fa_sheet: str | None = None,
    summary_sheet: str | None = None,
    lead_sheet: str | None = None,
    rollforward_sheet: str | None = None,
    addition_sheet: str | None = None,
    disposal_sheet: str | None = None,
    llm: bool | None = None,
) -> QcReport:
    """CSV 仅 FA list；Excel 走整本 workbook 流水线。"""
    from pathlib import Path

    from report.export_json import run_fa_list_qc
    from ingest.records import load_fa_list_csv

    p = Path(path)
    if p.suffix.lower() == ".csv":
        report = run_fa_list_qc(load_fa_list_csv(p), llm=llm)
        report.manual_review_sections = build_manual_review_sections(None)
        return report
    return run_workbook_qc_from_path(
        str(p),
        fa_sheet=fa_sheet,
        summary_sheet=summary_sheet,
        lead_sheet=lead_sheet,
        rollforward_sheet=rollforward_sheet,
        addition_sheet=addition_sheet,
        disposal_sheet=disposal_sheet,
        llm=llm,
    )
