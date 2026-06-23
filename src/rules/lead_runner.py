from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.lead_adjustment_internal_consistency import (
    check_lead_adjustment_internal_consistency,
)
from rules.lead_analysis_date_after_period_end import (
    check_lead_analysis_date_after_period_end,
)
from rules.lead_check_with_a3_row import check_lead_check_with_a3_row
from rules.lead_expectation_analysis import check_lead_expectation_analysis
from rules.lead_expectation_basis_present import check_lead_expectation_basis_present
from rules.lead_expectation_vs_movement_review import (
    check_lead_expectation_vs_movement_review,
)
from rules.lead_fluctuation_notes_refs import check_lead_fluctuation_notes_refs
from rules.lead_movement_consistency import check_lead_movement_consistency
from rules.lead_movement_notes_required import check_lead_movement_notes_required
from rules.lead_movement_rows_complete import check_lead_movement_rows_complete
from rules.lead_required_fields import check_lead_required_fields
from rules.lead_rollforward_tb_reconciliation import (
    check_lead_rollforward_tb_reconciliation,
)
from rules.lead_tt_gam_range import check_lead_tt_gam_range
from rules.lead_tt_overall_min import check_lead_tt_overall_min
from rules.lead_volatility_threshold_link import check_lead_volatility_threshold_link
from rules.materiality_consistency import check_materiality_consistency
from rules.models import QcIssue, Severity
from rules.risk_threshold_consistency import check_risk_threshold_consistency
from rules.unexpected_movement_investigation import check_unexpected_movement_investigation

LEAD_RULE_IDS: tuple[str, ...] = (
    "lead_required_fields",
    "lead_analysis_date_after_period_end",
    "materiality_consistency",
    "risk_threshold_consistency",
    "lead_tt_overall_min",
    "lead_tt_gam_range",
    "lead_expectation_analysis",
    "lead_expectation_basis_present",
    "lead_expectation_vs_movement_review",
    "lead_volatility_threshold_link",
    "lead_movement_rows_complete",
    "lead_movement_consistency",
    "lead_movement_notes_required",
    "lead_check_with_a3_row",
    "unexpected_movement_investigation",
    "lead_fluctuation_notes_refs",
    "lead_adjustment_internal_consistency",
    "lead_rollforward_tb_reconciliation",
)


def _lead_ingest_readability_issue(lead: LeadSheetDataset) -> list[QcIssue]:
    return [
        QcIssue(
            asset_id=None,
            rule_id="lead_ingest_readability",
            field="movement_table",
            severity=Severity.NEED_REVIEW,
            message="Lead movement table ingest is unreliable; dependent checks were paused.",
            suggestion="Review account rows, amount columns, Check with A3 / Diff, and Notes boundaries.",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
        )
    ]


def run_lead_rules(
    lead: LeadSheetDataset,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    strict_adjustment_total: bool | None = None,
    adjustment_layout_result: dict | None = None,
    adjustment_extracted_rows: list[dict] | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues: list[QcIssue] = []
    issues.extend(recorder.execute_rule("lead_required_fields", check_lead_required_fields, lead))
    if not lead.usable_for_rules:
        issues.extend(recorder.execute_rule("lead_ingest_readability", _lead_ingest_readability_issue, lead))
        for rule_id in LEAD_RULE_IDS:
            if rule_id != "lead_required_fields":
                recorder.record_data_insufficient(rule_id, "Lead movement table 读取不稳定，依赖 Lead 明细的检查未执行")
        return issues

    issues.extend(recorder.execute_rule("lead_analysis_date_after_period_end", check_lead_analysis_date_after_period_end, lead))
    issues.extend(recorder.execute_rule("materiality_consistency", check_materiality_consistency, lead))
    issues.extend(recorder.execute_rule("risk_threshold_consistency", check_risk_threshold_consistency, lead))
    issues.extend(recorder.execute_rule("lead_tt_overall_min", check_lead_tt_overall_min, lead))
    issues.extend(recorder.execute_rule("lead_tt_gam_range", check_lead_tt_gam_range, lead))
    issues.extend(recorder.execute_rule("lead_expectation_analysis", check_lead_expectation_analysis, lead))
    issues.extend(recorder.execute_rule("lead_expectation_basis_present", check_lead_expectation_basis_present, lead))
    issues.extend(recorder.execute_rule("lead_expectation_vs_movement_review", check_lead_expectation_vs_movement_review, lead))
    issues.extend(recorder.execute_rule("lead_volatility_threshold_link", check_lead_volatility_threshold_link, lead))
    issues.extend(recorder.execute_rule("lead_movement_rows_complete", check_lead_movement_rows_complete, lead))
    issues.extend(recorder.execute_rule("lead_movement_consistency", check_lead_movement_consistency, lead))
    issues.extend(recorder.execute_rule("lead_movement_notes_required", check_lead_movement_notes_required, lead))
    issues.extend(recorder.execute_rule("lead_check_with_a3_row", check_lead_check_with_a3_row, lead))
    issues.extend(recorder.execute_rule("unexpected_movement_investigation", check_unexpected_movement_investigation, lead))
    issues.extend(recorder.execute_rule("lead_fluctuation_notes_refs", check_lead_fluctuation_notes_refs, lead))
    issues.extend(
        recorder.execute_rule(
            "lead_adjustment_internal_consistency",
            check_lead_adjustment_internal_consistency,
            lead,
            strict_total=strict_adjustment_total,
            layout_result=adjustment_layout_result,
            extracted_rows=adjustment_extracted_rows,
        )
    )
    issues.extend(
        recorder.execute_rule(
            "lead_rollforward_tb_reconciliation",
            check_lead_rollforward_tb_reconciliation,
            lead,
            rollforward,
        )
    )
    return issues
