from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.reconciliation import ReconciliationCheck
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.models import QcIssue
from rules.rollforward_observations import (
    build_rollforward_abnormal_amounts_observation,
    build_rollforward_columns_complete_observation,
    build_rollforward_depreciation_pl_observation,
    build_rollforward_difference_over_sad_observation,
    build_rollforward_exists_observation,
)
from rules.rollforward_abnormal_amounts import check_rollforward_abnormal_amounts
from rules.rollforward_columns_complete import check_rollforward_columns_complete
from rules.rollforward_depreciation_pl_reconciliation import (
    check_rollforward_depreciation_pl_reconciliation,
)
from rules.rollforward_difference_over_sad import check_rollforward_difference_over_sad
from rules.rollforward_exists import check_rollforward_exists
from rules.rollforward_fa_list_reconciliation import (
    build_rollforward_fa_list_reconciliation_observation,
    check_rollforward_fa_list_reconciliation,
)

ROLLFORWARD_RULE_IDS: tuple[str, ...] = (
    "rollforward_exists",
    "rollforward_columns_complete",
    "rollforward_abnormal_amounts",
    "rollforward_fa_list_reconciliation",
    "rollforward_difference_over_sad",
    "rollforward_depreciation_pl_reconciliation",
    "rollforward_notes_semantic",
)


def run_rollforward_rules(
    rollforward: RollforwardSheetDataset | None,
    *,
    lead: LeadSheetDataset | None = None,
    reconciliations: list[ReconciliationCheck] | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues: list[QcIssue] = []
    exists_issues = recorder.execute_rule("rollforward_exists", check_rollforward_exists, rollforward)
    recorder.record_observation(
        "rollforward_exists",
        build_rollforward_exists_observation(rollforward, exists_issues),
    )
    issues.extend(exists_issues)
    columns_issues = recorder.execute_rule("rollforward_columns_complete", check_rollforward_columns_complete, rollforward)
    recorder.record_observation(
        "rollforward_columns_complete",
        build_rollforward_columns_complete_observation(rollforward, columns_issues),
    )
    issues.extend(columns_issues)
    abnormal_issues = recorder.execute_rule("rollforward_abnormal_amounts", check_rollforward_abnormal_amounts, rollforward)
    recorder.record_observation(
        "rollforward_abnormal_amounts",
        build_rollforward_abnormal_amounts_observation(rollforward, abnormal_issues),
    )
    issues.extend(abnormal_issues)
    issues.extend(
        recorder.execute_rule(
            "rollforward_fa_list_reconciliation",
            check_rollforward_fa_list_reconciliation,
            reconciliations,
            rollforward=rollforward,
            lead=lead,
            observation=build_rollforward_fa_list_reconciliation_observation(
                reconciliations,
                rollforward=rollforward,
                lead=lead,
            ),
        )
    )
    difference_issues = recorder.execute_rule("rollforward_difference_over_sad", check_rollforward_difference_over_sad, rollforward, lead=lead)
    recorder.record_observation(
        "rollforward_difference_over_sad",
        build_rollforward_difference_over_sad_observation(rollforward, lead, difference_issues),
    )
    issues.extend(difference_issues)
    depreciation_issues = recorder.execute_rule(
        "rollforward_depreciation_pl_reconciliation",
        check_rollforward_depreciation_pl_reconciliation,
        rollforward,
        lead=lead,
    )
    recorder.record_observation(
        "rollforward_depreciation_pl_reconciliation",
        build_rollforward_depreciation_pl_observation(rollforward, lead, depreciation_issues),
    )
    issues.extend(depreciation_issues)
    return issues
