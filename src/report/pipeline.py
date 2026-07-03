from __future__ import annotations

from pathlib import Path
from time import perf_counter

from ingest.workbook_context import WorkbookQcContext, load_workbook_context
from llm.config import LlmConfig, load_llm_config
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
    FINAL_DELIVERY_RULE_ID,
    FIRST_DELIVERY_RULE_ID,
    check_delivery_completion,
)
from rules.disposal_runner import DISPOSAL_RULE_IDS, run_disposal_rules
from rules.k03_runner import K03_RULE_IDS, run_k03_rules
from rules.lead_runner import LEAD_RULE_IDS, run_lead_rules
from rules.execution_recorder import RuleExecutionRecorder, validate_execution_ledger
from rules.models import ColumnContext
from rules.package_observations import build_k02_package_complete_observation
from rules.psp_observations import build_psp_completion_observation
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
    *DISPOSAL_RULE_IDS,
    *ADDITION_RULE_IDS,
    *K03_RULE_IDS,
    *LEAD_RULE_IDS,
    *ROLLFORWARD_RULE_IDS,
)


def run_workbook_qc(
    ctx: WorkbookQcContext,
    *,
    llm: bool | None = None,
    llm_config: LlmConfig | None = None,
    delivery_context: DeliveryCompletionContext | None = None,
) -> QcReport:
    qc_start = perf_counter()
    config = llm_config if llm_config is not None else load_llm_config(cli_enabled=llm)
    llm_seconds = 0.0
    llm_details = {}

    def record_llm_detail(key: str, label: str, seconds: float, calls: int = 1) -> None:
        detail = llm_details.setdefault(
            key,
            {"label": label, "seconds": 0.0, "calls": 0},
        )
        detail["seconds"] = float(detail["seconds"]) + max(seconds, 0.0)
        detail["calls"] = int(detail["calls"]) + max(calls, 0)

    def record_observed_issues(rule_issues: list) -> None:
        counts: dict[str, int] = {}
        for issue in rule_issues:
            counts[issue.rule_id] = counts.get(issue.rule_id, 0) + 1
        for rule_id, finding_count in counts.items():
            recorder.record(rule_id, finding_count)

    issues = []
    records = []
    recorder = RuleExecutionRecorder()
    ingest_review_results: list[dict] = []
    source_sheet = ""
    sheet_titles: list[str] | None = None
    wb_for_semantic: str | None = None

    if Path(ctx.source_file).suffix.lower() in (".xlsx", ".xlsm", ".xlsb"):
        wb_for_semantic = ctx.source_file
        if ctx.structure and ctx.structure.sheets_by_kind:
            sheet_titles = [
                sheet.sheet_name
                for sheets in ctx.structure.sheets_by_kind.values()
                for sheet in sheets
            ]

    if ctx.fa_list:
        fa_ctx = ColumnContext(
            mapped_fields={m.standard_field for m in ctx.fa_list.mapped_fields},
            mapped_headers={m.standard_field: m.source_header for m in ctx.fa_list.mapped_fields},
            mapped_columns={m.standard_field: m.column_index for m in ctx.fa_list.mapped_fields},
            source_sheet=ctx.fa_list.source_sheet,
            procedure_code="FA_LIST",
        )
        issues.extend(run_fa_list_rules(ctx.fa_list.records, fa_ctx, recorder=recorder))
        records = ctx.fa_list.records
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

        psp_raw_issues = recorder.execute_rule("psp_completion", check_psp_completion,
            ctx.summary,
            workbook_sheet_titles=sheet_titles,
            workbook_path=wb_for_psp,
            waiver_reason_reviewer=waiver_reason_reviewer,
            enforce_template_completeness=True,
        )
        recorder.record_observation(
            "psp_completion",
            build_psp_completion_observation(
                ctx.summary,
                psp_raw_issues,
                workbook_sheet_titles=sheet_titles,
            ),
        )
        if config.enabled and wb_for_psp and sheet_titles:
            llm_t0 = perf_counter()
            from llm.summary_psp_review import build_sheet_semantic_issues

            psp_semantic_issues = build_sheet_semantic_issues(
                ctx.summary,
                config,
                workbook_path=wb_for_psp,
                workbook_sheet_titles=sheet_titles,
            )
            record_observed_issues(psp_semantic_issues)
            psp_raw_issues.extend(psp_semantic_issues)
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
        addition_package_raw_issues = recorder.execute_rule(
            "addition_test_package_complete",
            check_addition_test_package,
                ctx.summary,
                workbook_sheet_titles=sheet_titles,
                workbook_path=ctx.source_file,
                test_sheet_note=ctx.addition_test.waiver_note_text
                if ctx.addition_test
                else None,
        )
        recorder.record_observation(
            "addition_test_package_complete",
            build_k02_package_complete_observation(
                ctx.summary,
                addition_package_raw_issues,
                workbook_sheet_titles=sheet_titles,
                test_sheet_note=ctx.addition_test.waiver_note_text
                if ctx.addition_test
                else None,
                kind="addition",
            ),
        )
        addition_package_issues = attach_rule_metadata(addition_package_raw_issues)
        issues.extend(addition_package_issues)
        disposal_package_raw_issues = recorder.execute_rule(
            "disposal_test_package_complete",
            check_disposal_test_package,
                ctx.summary,
                workbook_sheet_titles=sheet_titles,
                workbook_path=ctx.source_file,
                test_sheet_note=ctx.disposal_test.waiver_note_text
                if ctx.disposal_test
                else None,
        )
        recorder.record_observation(
            "disposal_test_package_complete",
            build_k02_package_complete_observation(
                ctx.summary,
                disposal_package_raw_issues,
                workbook_sheet_titles=sheet_titles,
                test_sheet_note=ctx.disposal_test.waiver_note_text
                if ctx.disposal_test
                else None,
                kind="disposal",
            ),
        )
        disposal_package_issues = attach_rule_metadata(disposal_package_raw_issues)
        issues.extend(disposal_package_issues)
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
            recorder=recorder,
        )
        if config.enabled:
            llm_t0 = perf_counter()
            llm_lead_issues = build_lead_semantic_issues(
                ctx.lead,
                config,
                semantic_context=lead_semantic_context or {},
            )
            record_observed_issues(llm_lead_issues)
            record_observed_issues(lead_adj_issues)
            lead_raw_issues.extend(llm_lead_issues)
            lead_raw_issues.extend(lead_adj_issues)
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
                recorder=recorder,
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
            record_observed_issues(addition_llm_issues)
            addition_issues.extend(addition_llm_issues)
            elapsed = perf_counter() - llm_t0
            llm_seconds += elapsed
            record_llm_detail(
                "addition_semantic",
                "K.02.1 addition semantic review",
                elapsed,
            )
        issues.extend(addition_issues)
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
            record_observed_issues(addition_llm_issues)
            addition_issues.extend(addition_llm_issues)
            issues.extend(addition_llm_issues)
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

    disposal_issues = attach_rule_metadata(
        run_disposal_rules(
            disposal_test=ctx.disposal_test,
            disposal_sample_output=ctx.disposal_sample_output,
            disposal_execution_path=ctx.disposal_execution_path,
            disposal_list=ctx.disposal_list,
            disposal_list_summary=ctx.disposal_list_summary,
            rollforward=ctx.rollforward,
            lead=ctx.lead,
            recorder=recorder,
        )
    )
    if config.enabled and (
        ctx.disposal_list_summary
        or ctx.disposal_test
        or ctx.disposal_sample_output
        or ctx.disposal_execution_path
    ):
        llm_t0 = perf_counter()
        from llm.disposal_review import (
            RULE_ID as DISPOSAL_LLM_RULE,
            build_disposal_llm_issues,
        )

        disposal_llm_issues = attach_rule_metadata(
            build_disposal_llm_issues(
                config,
                disposal_list_summary=ctx.disposal_list_summary,
                disposal_test=ctx.disposal_test,
                disposal_sample_output=ctx.disposal_sample_output,
                disposal_execution_path=ctx.disposal_execution_path,
                prior_issues=disposal_issues,
            )
        )
        record_observed_issues(disposal_llm_issues)
        disposal_issues.extend(disposal_llm_issues)
        elapsed = perf_counter() - llm_t0
        llm_seconds += elapsed
        record_llm_detail(
            "disposal_semantic",
            "K.02.2 disposal semantic review",
            elapsed,
        )
    issues.extend(disposal_issues)

    k03_issues = attach_rule_metadata(
        run_k03_rules(
            ctx.k03_sheets,
            lead=ctx.lead,
            rollforward=ctx.rollforward,
            fa_list=ctx.fa_list,
            recorder=recorder,
        )
    )
    issues.extend(k03_issues)
    if not source_sheet and ctx.k03_sheets:
        source_sheet = ctx.k03_sheets[0].sheet_name

    rollforward_sheet_section = None
    if config.enabled:
        llm_t0 = perf_counter()
        from llm.ingest_review import run_workbook_ingest_reviews

        for result in run_workbook_ingest_reviews(
            config,
            lead=ctx.lead,
            rollforward=ctx.rollforward,
            disposal_test=ctx.disposal_test,
            disposal_sample_output=ctx.disposal_sample_output,
            disposal_execution_path=ctx.disposal_execution_path,
            workbook_path=ctx.source_file,
            workbook_sheet_titles=sheet_titles,
            recognized_sheet_kinds=_recognized_ingest_sheet_kinds(ctx),
        ):
            item = result.to_dict()
            item.update(
                {
                    "procedure_code": item.get("procedure_code") or "WORKBOOK",
                    "source_sheet": item.get("source_sheet") or item.get("candidate_sheet") or "",
                    "review_type": item.get("review_type") or "ingest_review",
                    "note": "读取结果复核提示，不等同于业务规则 finding。",
                }
            )
            ingest_review_results.append(item)
        elapsed = perf_counter() - llm_t0
        llm_seconds += elapsed
        if ingest_review_results:
            record_llm_detail(
                "ingest_review",
                "读取结果复核",
                elapsed,
                calls=len(ingest_review_results),
            )

    if ctx.rollforward:
        rollforward_raw_issues = run_rollforward_rules(
            ctx.rollforward,
            lead=ctx.lead,
            reconciliations=ctx.reconciliations,
            recorder=recorder,
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
            record_observed_issues(rf_note_issues)
            rollforward_raw_issues.extend(rf_note_issues)
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
        if not source_sheet:
            source_sheet = ctx.rollforward.source_sheet

    if delivery_context:
        delivery_rule_id = (
            FIRST_DELIVERY_RULE_ID
            if delivery_context.stage == "first"
            else FINAL_DELIVERY_RULE_ID
        )
        delivery_raw_issues = recorder.execute_rule(delivery_rule_id, check_delivery_completion,
            delivery_context,
            prior_issues=issues,
            workbook_context=ctx,
            workbook_path=ctx.source_file,
            workbook_sheet_titles=sheet_titles,
        )
        delivery_issues = attach_rule_metadata(delivery_raw_issues)
        issues.extend(delivery_issues)

    execution_ledger = recorder.to_ledger()
    validate_execution_ledger(execution_ledger, issues)

    report = build_report(
        source_file=ctx.source_file,
        source_sheet=source_sheet or "workbook",
        procedure_code="WORKBOOK",
        rule_ids=recorder.executed_rule_ids(),
        records=records,
        issues=issues,
        summary_sheet_section=summary_sheet_section,
        lead_sheet_section=lead_sheet_section,
        rollforward_sheet_section=rollforward_sheet_section,
        addition_sheet_section=addition_sheet_section,
        execution_ledger=execution_ledger,
        ingest_review_section=(
            {
                "description": "读取结果复核提示（LLM 辅助，不等同于业务规则 finding）。",
                "reviews": ingest_review_results,
            }
            if ingest_review_results
            else None
        ),
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


def _recognized_ingest_sheet_kinds(ctx: WorkbookQcContext) -> dict[str, bool]:
    """Sheet kinds already recognized by deterministic ingest or structure scan."""
    recognized = {
        "summary": ctx.summary is not None,
        "lead": ctx.lead is not None,
        "rollforward": ctx.rollforward is not None,
        "fa_list": ctx.fa_list is not None,
        "addition_list": ctx.addition_list is not None,
        "addition_test": ctx.addition_test is not None,
        "addition_sample_output": ctx.addition_sample_output is not None,
        "disposal_list": ctx.disposal_list is not None,
        "disposal_test": ctx.disposal_test is not None,
        "disposal_sample_output": ctx.disposal_sample_output is not None,
    }
    if ctx.structure:
        for kind, sheets in ctx.structure.sheets_by_kind.items():
            if sheets:
                recognized[kind] = True
    return recognized


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
    llm_config: LlmConfig | None = None,
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
    report = run_workbook_qc(
        ctx,
        llm=llm,
        llm_config=llm_config,
        delivery_context=delivery_context,
    )
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
    llm_config: LlmConfig | None = None,
    delivery_context: DeliveryCompletionContext | None = None,
) -> QcReport:
    """CSV 仅 FA list；Excel 走整本 workbook 流水线。"""
    from pathlib import Path

    from report.export_json import run_fa_list_qc
    from ingest.records import load_fa_list_csv

    p = Path(path)
    if p.suffix.lower() == ".csv":
        report = run_fa_list_qc(
            load_fa_list_csv(p),
            llm=llm,
            llm_config=llm_config,
        )
        if delivery_context:
            delivery_recorder = RuleExecutionRecorder()
            delivery_rule_id = (
                FIRST_DELIVERY_RULE_ID
                if delivery_context.stage == "first"
                else FINAL_DELIVERY_RULE_ID
            )
            delivery_issues = attach_rule_metadata(
                delivery_recorder.execute_rule(
                    delivery_rule_id,
                    check_delivery_completion,
                    delivery_context,
                    prior_issues=report.issues,
                )
            )
            if delivery_issues:
                report.issues.extend(delivery_issues)
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
            base_items = list((report.execution_ledger or {}).get("items", []))
            base_items.extend(delivery_recorder.to_ledger().get("items", []))
            executed = sum(1 for item in base_items if item.get("status") == "EXECUTED")
            data_insufficient = sum(
                1 for item in base_items if item.get("status") == "DATA_INSUFFICIENT"
            )
            not_applicable = sum(
                1 for item in base_items if item.get("status") == "NOT_APPLICABLE"
            )
            rules_with_findings = sum(
                1
                for item in base_items
                if item.get("status") == "EXECUTED" and item.get("finding_count", 0) > 0
            )
            report.execution_ledger = {
                "summary": {
                    "total_observed_checkpoints": len(base_items),
                    "executed": executed,
                    "data_insufficient": data_insufficient,
                    "not_applicable": not_applicable,
                    "executed_rules": executed,
                    "rules_with_findings": rules_with_findings,
                    "rules_without_findings": executed - rules_with_findings,
                },
                "items": base_items,
            }
            report.rule_ids = [item["rule_id"] for item in base_items]
            validate_execution_ledger(report.execution_ledger, report.issues)
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
        llm_config=llm_config,
        delivery_context=delivery_context,
    )
