from __future__ import annotations

from pathlib import Path
from time import perf_counter

from ingest.workbook_context import WorkbookQcContext, load_workbook_context
from ingest.workbook_reader import list_workbook_sheet_titles
from llm.config import load_llm_config
from llm.review import enrich_report_with_llm
from report.manual_review import build_manual_review_sections
from report.addition_test_report import build_addition_sheet_section
from report.summary import QcReport, build_report, worst_severity
from report.lead_sheet_report import build_lead_sheet_section
from report.rollforward_sheet_report import build_rollforward_sheet_section
from report.summary_sheet_report import build_summary_sheet_section
from rules.addition_test_package import (
    check_addition_test_package,
    check_disposal_test_package,
)
from rules.addition_runner import ADDITION_RULE_IDS, run_addition_rules
from rules.delivery_completion import (
    DeliveryCompletionContext,
    check_delivery_completion,
)
from rules.lead_runner import LEAD_RULE_IDS, run_lead_rules
from rules.models import ColumnContext
from rules.psp_completion import check_psp_completion
from rules.registry import attach_rule_metadata
from rules.rollforward_runner import ROLLFORWARD_RULE_IDS, run_rollforward_rules
from rules.runner import FA_LIST_RULE_IDS, run_fa_list_rules

WORKBOOK_RULE_IDS = (
    *FA_LIST_RULE_IDS,
    "psp_completion",
    "addition_test_package_complete",
    "disposal_test_package_complete",
    "first_delivery_standard",
    "final_delivery_standard",
    *ADDITION_RULE_IDS,
    *LEAD_RULE_IDS,
    *ROLLFORWARD_RULE_IDS,
)


def run_workbook_qc(
    ctx: WorkbookQcContext,
    *,
    llm: bool | None = None,
    delivery_context: DeliveryCompletionContext | None = None,
) -> QcReport:
    qc_start = perf_counter()
    config = load_llm_config(cli_enabled=llm)
    llm_seconds = 0.0
    llm_details = {}

    def record_llm_detail(key: str, label: str, seconds: float, calls: int = 1) -> None:
        detail = llm_details.setdefault(
            key,
            {"label": label, "seconds": 0.0, "calls": 0},
        )
        detail["seconds"] = float(detail["seconds"]) + max(seconds, 0.0)
        detail["calls"] = int(detail["calls"]) + max(calls, 0)

    issues = []
    records = []
    rule_ids: list[str] = []
    source_sheet = ""
    sheet_titles: list[str] | None = None
    wb_for_semantic: str | None = None

    if Path(ctx.source_file).suffix.lower() in (".xlsx", ".xlsm", ".xlsb"):
        wb_for_semantic = ctx.source_file
        try:
            sheet_titles = list_workbook_sheet_titles(ctx.source_file)
        except Exception:
            sheet_titles = None
            wb_for_semantic = None

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
        wb_for_psp: str | None = wb_for_semantic
        waiver_reason_reviewer = None
        if config.enabled:
            llm_t0 = perf_counter()
            from llm.summary_psp_review import (
                build_waiver_semantic_context,
                review_waiver_reasons_batch_with_llm,
            )

            waiver_semantic_context = build_waiver_semantic_context(
                lead=ctx.lead,
                rollforward=ctx.rollforward,
                addition_list=ctx.addition_list,
                disposal_list=ctx.disposal_list,
                reconciliations=ctx.reconciliations,
                workbook_sheet_titles=sheet_titles,
            )

            waiver_target_count = sum(
                1 for row in ctx.summary.programs if (row.waiver_reason or "").strip()
            )
            waiver_reviews = review_waiver_reasons_batch_with_llm(
                ctx.summary.programs,
                config,
                semantic_context=waiver_semantic_context,
            )
            waiver_reviews_by_id = {
                id(ctx.summary.programs[idx]): review
                for idx, review in waiver_reviews.items()
                if 0 <= idx < len(ctx.summary.programs)
            }

            def waiver_reason_reviewer(row):
                return waiver_reviews_by_id.get(id(row))
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            if waiver_target_count:
                record_llm_detail(
                    "summary_waiver_reason",
                    "汇总页 PSP 拒绝理由",
                    elapsed,
                )

        psp_raw_issues = check_psp_completion(
            ctx.summary,
            workbook_sheet_titles=sheet_titles,
            workbook_path=wb_for_psp,
            waiver_reason_reviewer=waiver_reason_reviewer,
            enforce_template_completeness=True,
        )
        if config.enabled and wb_for_psp and sheet_titles:
            llm_t0 = perf_counter()
            from llm.summary_psp_review import build_sheet_semantic_issues

            psp_raw_issues.extend(
                build_sheet_semantic_issues(
                    ctx.summary,
                    config,
                    workbook_path=wb_for_psp,
                    workbook_sheet_titles=sheet_titles,
                )
            )
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            record_llm_detail(
                "summary_sheet_semantic",
                "汇总页 sheet 语义匹配",
                elapsed,
            )
        psp_issues = attach_rule_metadata(psp_raw_issues)
        issues.extend(psp_issues)
        summary_sheet_section = build_summary_sheet_section(ctx.summary, psp_issues)
        rule_ids.append("psp_completion")
        addition_package_issues = attach_rule_metadata(
            check_addition_test_package(
                ctx.summary,
                workbook_sheet_titles=sheet_titles,
                workbook_path=ctx.source_file,
            )
        )
        issues.extend(addition_package_issues)
        rule_ids.append("addition_test_package_complete")
        disposal_package_issues = attach_rule_metadata(
            check_disposal_test_package(
                ctx.summary,
                workbook_sheet_titles=sheet_titles,
                workbook_path=ctx.source_file,
            )
        )
        issues.extend(disposal_package_issues)
        rule_ids.append("disposal_test_package_complete")
        if not source_sheet:
            source_sheet = ctx.summary.source_sheet
    else:
        summary_sheet_section = None

    lead_sheet_section = None
    if ctx.lead:
        adjustment_layout_result = None
        adjustment_extracted_rows = None
        strict_adjustment_total = None
        lead_adj_issues: list = []
        lead_semantic_context = None

        if config.enabled:
            llm_t0 = perf_counter()
            from llm.lead_adjustment_review import (
                RULE_LAYOUT,
                RULE_SEMANTIC,
                extract_layout_and_rows_for_gating,
                run_lead_adjustment_llm_review,
                should_review_adjustments,
            )
            from llm.lead_review import (
                RULE_EXPECTATION,
                RULE_FLUCTUATION,
                build_lead_semantic_context,
                build_lead_semantic_issues,
            )
            from rules.lead_adjustment_gating import should_run_strict_total_check

            lead_semantic_context = build_lead_semantic_context(
                summary=ctx.summary,
                rollforward=ctx.rollforward,
                addition_list=ctx.addition_list,
                disposal_list=ctx.disposal_list,
                reconciliations=ctx.reconciliations,
                workbook_sheet_titles=sheet_titles,
            )

            if should_review_adjustments(ctx.lead):
                lead_adj_issues, adj_review = run_lead_adjustment_llm_review(
                    ctx.lead,
                    config,
                    workbook_path=ctx.source_file,
                    workbook_context=lead_semantic_context,
                )
                if adj_review:
                    adjustment_layout_result, adjustment_extracted_rows = (
                        extract_layout_and_rows_for_gating(adj_review)
                    )
                    strict_adjustment_total = should_run_strict_total_check(
                        ctx.lead,
                        layout_result=adjustment_layout_result,
                        extracted_rows=adjustment_extracted_rows,
                    )
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            record_llm_detail(
                "lead_adjustment_semantic",
                "Lead 调整分录 LLM",
                elapsed,
            )

        lead_raw_issues = run_lead_rules(
            ctx.lead,
            rollforward=ctx.rollforward,
            strict_adjustment_total=strict_adjustment_total,
            adjustment_layout_result=adjustment_layout_result,
            adjustment_extracted_rows=adjustment_extracted_rows,
        )
        if config.enabled:
            llm_t0 = perf_counter()
            llm_lead_issues = build_lead_semantic_issues(
                ctx.lead,
                config,
                semantic_context=lead_semantic_context or {},
            )
            lead_raw_issues.extend(llm_lead_issues)
            lead_raw_issues.extend(lead_adj_issues)
            if llm_lead_issues:
                for rid in (RULE_EXPECTATION, RULE_FLUCTUATION):
                    if rid not in rule_ids:
                        rule_ids.append(rid)
            if lead_adj_issues:
                for rid in (RULE_LAYOUT, RULE_SEMANTIC):
                    if rid not in rule_ids:
                        rule_ids.append(rid)
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            record_llm_detail(
                "lead_semantic",
                "Lead 预期/波动说明",
                elapsed,
            )
        lead_issues = attach_rule_metadata(lead_raw_issues)
        issues.extend(lead_issues)
        lead_sheet_section = build_lead_sheet_section(ctx.lead, lead_issues)
        rule_ids.extend(list(LEAD_RULE_IDS))
        if not source_sheet:
            source_sheet = ctx.lead.source_sheet

    addition_llm_issues = []
    if ctx.addition_list:
        addition_issues = attach_rule_metadata(
            run_addition_rules(
                ctx.addition_list,
                rollforward=ctx.rollforward,
                lead=ctx.lead,
                addition_test=ctx.addition_test,
                addition_sample_output=ctx.addition_sample_output,
                addition_execution_path=ctx.addition_execution_path,
            )
        )
        if config.enabled:
            llm_t0 = perf_counter()
            from llm.addition_review import (
                RULE_ID as ADDITION_LLM_RULE,
                build_addition_llm_issues,
            )

            addition_llm_issues = attach_rule_metadata(
                build_addition_llm_issues(
                    config,
                    addition_list=ctx.addition_list,
                    addition_test=ctx.addition_test,
                    addition_sample_output=ctx.addition_sample_output,
                    addition_execution_path=ctx.addition_execution_path,
                    prior_issues=addition_issues,
                )
            )
            addition_issues.extend(addition_llm_issues)
            if addition_llm_issues and ADDITION_LLM_RULE not in rule_ids:
                rule_ids.append(ADDITION_LLM_RULE)
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            record_llm_detail(
                "addition_semantic",
                "K.02.1 addition semantic review",
                elapsed,
            )
        issues.extend(addition_issues)
        rule_ids.extend(list(ADDITION_RULE_IDS))
        addition_sheet_section = build_addition_sheet_section(
            ctx.addition_test,
            ctx.addition_sample_output,
            ctx.addition_execution_path,
            addition_issues,
        )
        if not source_sheet:
            source_sheet = ctx.addition_list.source_sheet
    else:
        addition_issues = []
        if config.enabled and (
            ctx.addition_test or ctx.addition_sample_output or ctx.addition_execution_path
        ):
            llm_t0 = perf_counter()
            from llm.addition_review import (
                RULE_ID as ADDITION_LLM_RULE,
                build_addition_llm_issues,
            )

            addition_llm_issues = attach_rule_metadata(
                build_addition_llm_issues(
                    config,
                    addition_list=None,
                    addition_test=ctx.addition_test,
                    addition_sample_output=ctx.addition_sample_output,
                    addition_execution_path=ctx.addition_execution_path,
                    prior_issues=[],
                )
            )
            addition_issues.extend(addition_llm_issues)
            issues.extend(addition_llm_issues)
            if addition_llm_issues and ADDITION_LLM_RULE not in rule_ids:
                rule_ids.append(ADDITION_LLM_RULE)
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            record_llm_detail(
                "addition_semantic",
                "K.02.1 addition semantic review",
                elapsed,
            )
        addition_sheet_section = build_addition_sheet_section(
            ctx.addition_test,
            ctx.addition_sample_output,
            ctx.addition_execution_path,
            addition_issues,
        )

    rollforward_sheet_section = None
    if ctx.rollforward:
        rollforward_raw_issues = run_rollforward_rules(
            ctx.rollforward,
            lead=ctx.lead,
            reconciliations=ctx.reconciliations,
        )
        if config.enabled:
            llm_t0 = perf_counter()
            from llm.lead_review import build_lead_semantic_context
            from llm.rollforward_notes_review import (
                RULE_ID as RF_NOTES_RULE,
                build_rollforward_notes_issues,
            )

            rf_semantic_context = build_lead_semantic_context(
                summary=ctx.summary,
                rollforward=ctx.rollforward,
                addition_list=ctx.addition_list,
                disposal_list=ctx.disposal_list,
                reconciliations=ctx.reconciliations,
                workbook_sheet_titles=sheet_titles,
            )
            rf_note_issues = build_rollforward_notes_issues(
                ctx.rollforward,
                config,
                lead=ctx.lead,
                prior_issues=rollforward_raw_issues,
                workbook_context=rf_semantic_context,
            )
            rollforward_raw_issues.extend(rf_note_issues)
            if rf_note_issues and RF_NOTES_RULE not in rule_ids:
                rule_ids.append(RF_NOTES_RULE)
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            record_llm_detail(
                "rollforward_notes_semantic",
                "K.01 后推说明",
                elapsed,
            )
        rollforward_issues = attach_rule_metadata(rollforward_raw_issues)
        issues.extend(rollforward_issues)
        rollforward_sheet_section = build_rollforward_sheet_section(
            ctx.rollforward, rollforward_issues
        )
        rule_ids.extend(list(ROLLFORWARD_RULE_IDS))
        if not source_sheet:
            source_sheet = ctx.rollforward.source_sheet

    if delivery_context:
        delivery_raw_issues = check_delivery_completion(
            delivery_context,
            prior_issues=issues,
            workbook_context=ctx,
            workbook_path=ctx.source_file,
            workbook_sheet_titles=sheet_titles,
        )
        delivery_issues = attach_rule_metadata(delivery_raw_issues)
        issues.extend(delivery_issues)
        if delivery_context.stage == "first":
            rule_ids.append("first_delivery_standard")
        elif delivery_context.stage == "final":
            rule_ids.append("final_delivery_standard")

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
        addition_sheet_section=addition_sheet_section,
    )
    report.manual_review_sections = build_manual_review_sections(ctx.lead)

    if config.enabled:
        llm_t0 = perf_counter()
        report = enrich_report_with_llm(
            report,
            config,
            summary=ctx.summary,
            workbook=ctx,
        )
        elapsed = perf_counter() - llm_t0
        llm_seconds += elapsed
        record_llm_detail(
            "report_enrichment",
            "最终报告摘要",
            elapsed,
        )
    qc_seconds = perf_counter() - qc_start
    report.runtime_timings.update(
        {
            "rules_seconds": round(max(qc_seconds - llm_seconds, 0.0), 3),
            "llm_seconds": round(llm_seconds, 3),
            "llm_enabled": bool(config.enabled),
            "llm_details": [
                {
                    "key": key,
                    "label": detail["label"],
                    "seconds": round(float(detail["seconds"]), 3),
                    "calls": int(detail["calls"]),
                }
                for key, detail in llm_details.items()
            ],
        }
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
    delivery_context: DeliveryCompletionContext | None = None,
) -> QcReport:
    ingest_t0 = perf_counter()
    ctx = load_workbook_context(
        path,
        fa_sheet=fa_sheet,
        summary_sheet=summary_sheet,
        lead_sheet=lead_sheet,
        rollforward_sheet=rollforward_sheet,
        addition_sheet=addition_sheet,
        disposal_sheet=disposal_sheet,
    )
    ingest_seconds = perf_counter() - ingest_t0
    report = run_workbook_qc(ctx, llm=llm, delivery_context=delivery_context)
    report.runtime_timings.update({"ingest_seconds": round(ingest_seconds, 3)})
    return report


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
    delivery_context: DeliveryCompletionContext | None = None,
) -> QcReport:
    """CSV 仅 FA list；Excel 走整本 workbook 流水线。"""
    from pathlib import Path

    from report.export_json import run_fa_list_qc
    from ingest.records import load_fa_list_csv

    p = Path(path)
    if p.suffix.lower() == ".csv":
        report = run_fa_list_qc(load_fa_list_csv(p), llm=llm)
        delivery_issues = attach_rule_metadata(
            check_delivery_completion(
                delivery_context,
                prior_issues=report.issues,
            )
        )
        if delivery_issues:
            report.issues.extend(delivery_issues)
            if delivery_context and delivery_context.stage == "first":
                report.rule_ids.append("first_delivery_standard")
            elif delivery_context and delivery_context.stage == "final":
                report.rule_ids.append("final_delivery_standard")
            for issue in delivery_issues:
                if issue.severity.value == "FAIL":
                    report.summary.fail_count += 1
                elif issue.severity.value == "WARN":
                    report.summary.warn_count += 1
                elif issue.severity.value == "NEED_REVIEW":
                    report.summary.need_review_count += 1
                report.summary.by_rule[issue.rule_id] = (
                    report.summary.by_rule.get(issue.rule_id, 0) + 1
                )
            all_severities = [i.severity for i in report.issues]
            report.summary.overall_severity = worst_severity(all_severities)
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
        delivery_context=delivery_context,
    )
