from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
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
from rules.models import QcIssue
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


def run_lead_rules(
    lead: LeadSheetDataset,
    *,
    rollforward: RollforwardSheetDataset | None = None,
) -> list[QcIssue]:
    """执行全部 Lead 相关规则（不含 attach_rule_metadata）。"""
    issues: list[QcIssue] = []
    issues.extend(check_lead_required_fields(lead))
    issues.extend(check_lead_analysis_date_after_period_end(lead))
    issues.extend(check_materiality_consistency(lead))
    issues.extend(check_risk_threshold_consistency(lead))
    issues.extend(check_lead_tt_overall_min(lead))
    issues.extend(check_lead_tt_gam_range(lead))
    issues.extend(check_lead_expectation_analysis(lead))
    issues.extend(check_lead_expectation_basis_present(lead))
    issues.extend(check_lead_expectation_vs_movement_review(lead))
    issues.extend(check_lead_volatility_threshold_link(lead))
    issues.extend(check_lead_movement_rows_complete(lead))
    issues.extend(check_lead_movement_consistency(lead))
    issues.extend(check_lead_movement_notes_required(lead))
    issues.extend(check_lead_check_with_a3_row(lead))
    issues.extend(check_unexpected_movement_investigation(lead))
    issues.extend(check_lead_fluctuation_notes_refs(lead))
    issues.extend(check_lead_adjustment_internal_consistency(lead))
    issues.extend(check_lead_rollforward_tb_reconciliation(lead, rollforward))
    return issues
