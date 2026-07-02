from __future__ import annotations

from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalSampleOutputDataset,
    DisposalTestSheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import DisposalListSummary, FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.disposal_consistency import check_disposal_sample_match
from rules.disposal_detailed_test import RULE_IDS as DISPOSAL_DETAILED_RULE_IDS
from rules.disposal_detailed_test import run_disposal_detailed_test_rules
from rules.disposal_list_rules import RULE_IDS as DISPOSAL_LIST_RULE_IDS
from rules.disposal_list_rules import run_disposal_list_rules
from rules.disposal_observations import (
    build_disposal_list_net_value_observation,
    build_disposal_net_value_recalculation_observation,
    build_disposal_reconciliation_formula_source_observation,
    build_disposal_reconciliation_readability_observation,
    build_disposal_required_fields_observation,
    build_disposal_rollforward_reconciliation_observation,
    build_disposal_sample_match_observation,
    build_disposal_sample_pool_observation,
)
from rules.disposal_reconciliation import RULE_IDS as DISPOSAL_RECONCILIATION_RULE_IDS
from rules.disposal_reconciliation import run_disposal_reconciliation_rules
from rules.disposal_sampling_output import RULE_IDS as DISPOSAL_SAMPLING_RULE_IDS
from rules.disposal_sampling_output import run_disposal_sampling_rules
from rules.execution_recorder import RuleExecutionRecorder
from rules.models import QcIssue

DISPOSAL_RULE_IDS: tuple[str, ...] = (
    "disposal_sample_match",
    *DISPOSAL_RECONCILIATION_RULE_IDS,
    *DISPOSAL_LIST_RULE_IDS,
    *DISPOSAL_SAMPLING_RULE_IDS,
    *DISPOSAL_DETAILED_RULE_IDS,
)


def run_disposal_rules(
    *,
    disposal_test: DisposalTestSheetDataset | None = None,
    disposal_sample_output: DisposalSampleOutputDataset | None = None,
    disposal_execution_path: DisposalExecutionPathDataset | None = None,
    disposal_list: FaListDataset | None = None,
    disposal_list_summary: DisposalListSummary | None = None,
    rollforward: RollforwardSheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues: list[QcIssue] = []
    reconciliation_issues = run_disposal_reconciliation_rules(
        disposal_list_summary=disposal_list_summary,
        disposal_test=disposal_test,
        disposal_execution_path=disposal_execution_path,
        rollforward=rollforward,
        lead=lead,
        recorder=recorder,
    )
    _record_disposal_reconciliation_observations(
        recorder,
        disposal_list_summary=disposal_list_summary,
        disposal_test=disposal_test,
        rollforward=rollforward,
        lead=lead,
        issues=reconciliation_issues,
    )
    issues.extend(reconciliation_issues)
    if not disposal_execution_path or disposal_execution_path.path_kind != "summary_waived":
        list_issues = run_disposal_list_rules(
            disposal_list,
            disposal_list_summary,
            lead=lead,
            recorder=recorder,
        )
        _record_disposal_list_observations(
            recorder,
            disposal_list=disposal_list,
            issues=list_issues,
        )
        issues.extend(list_issues)
    else:
        for rule_id in DISPOSAL_LIST_RULE_IDS:
            recorder.record_not_applicable(rule_id, "处置测试已豁免，处置清单检查暂不适用")
    if not disposal_execution_path or disposal_execution_path.path_kind not in {
        "summary_waived",
        "test_sheet_waiver_note",
    }:
        sampling_issues = run_disposal_sampling_rules(
            disposal_list_summary=disposal_list_summary,
            disposal_test=disposal_test,
            disposal_sample_output=disposal_sample_output,
            lead=lead,
            recorder=recorder,
        )
        _record_disposal_sampling_observations(
            recorder,
            disposal_list_summary=disposal_list_summary,
            disposal_sample_output=disposal_sample_output,
            issues=sampling_issues,
        )
        issues.extend(sampling_issues)
        issues.extend(run_disposal_detailed_test_rules(disposal_test, recorder=recorder))
    else:
        for rule_id in (*DISPOSAL_SAMPLING_RULE_IDS, *DISPOSAL_DETAILED_RULE_IDS):
            recorder.record_not_applicable(rule_id, "处置测试已豁免或测试表注明不执行")
    sample_match_issues = recorder.execute_rule(
        "disposal_sample_match",
        check_disposal_sample_match,
        disposal_test,
        disposal_sample_output,
        execution_path=disposal_execution_path,
    )
    recorder.record_observation(
        "disposal_sample_match",
        build_disposal_sample_match_observation(
            disposal_test,
            disposal_sample_output,
            disposal_execution_path,
            sample_match_issues,
        ),
    )
    issues.extend(sample_match_issues)
    return issues


def _record_disposal_reconciliation_observations(
    recorder: RuleExecutionRecorder,
    *,
    disposal_list_summary: DisposalListSummary | None,
    disposal_test: DisposalTestSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
    lead: LeadSheetDataset | None,
    issues: list[QcIssue],
) -> None:
    _record_if_present(
        recorder,
        "disposal_reconciliation_readability",
        build_disposal_reconciliation_readability_observation(
            disposal_test,
            _issues_for(issues, "disposal_reconciliation_readability"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_reconciliation_formula_source",
        build_disposal_reconciliation_formula_source_observation(
            disposal_test,
            _issues_for(issues, "disposal_reconciliation_formula_source"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_net_value_recalculation",
        build_disposal_net_value_recalculation_observation(
            disposal_test,
            _issues_for(issues, "disposal_net_value_recalculation"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_rollforward_reconciliation",
        build_disposal_rollforward_reconciliation_observation(
            disposal_list_summary,
            disposal_test,
            rollforward,
            lead,
            _issues_for(issues, "disposal_rollforward_reconciliation"),
        ),
    )


def _record_disposal_list_observations(
    recorder: RuleExecutionRecorder,
    *,
    disposal_list: FaListDataset | None,
    issues: list[QcIssue],
) -> None:
    _record_if_present(
        recorder,
        "disposal_required_fields",
        build_disposal_required_fields_observation(
            disposal_list,
            _issues_for(issues, "disposal_required_fields"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_list_net_value_recalculation",
        build_disposal_list_net_value_observation(
            disposal_list,
            _issues_for(issues, "disposal_list_net_value_recalculation"),
        ),
    )


def _record_disposal_sampling_observations(
    recorder: RuleExecutionRecorder,
    *,
    disposal_list_summary: DisposalListSummary | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
    issues: list[QcIssue],
) -> None:
    _record_if_present(
        recorder,
        "disposal_sample_pool_amount_match",
        build_disposal_sample_pool_observation(
            disposal_list_summary,
            disposal_sample_output,
            _issues_for(issues, "disposal_sample_pool_amount_match"),
        ),
    )


def _record_if_present(
    recorder: RuleExecutionRecorder,
    rule_id: str,
    observation: dict,
) -> None:
    if rule_id in recorder.executed_rule_ids():
        recorder.record_observation(rule_id, observation)


def _issues_for(issues: list[QcIssue], rule_id: str) -> list[QcIssue]:
    return [issue for issue in issues if issue.rule_id == rule_id]
