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
from rules.disposal_list_rules import (
    check_disposal_method_classification,
    check_disposal_other_reduction_over_tt,
    check_disposal_required_fields,
    check_disposal_list_net_values,
    run_disposal_list_rules,
)
from rules.disposal_observations import (
    build_disposal_difference_investigation_observation,
    build_disposal_exception_followup_observation,
    build_disposal_list_net_value_observation,
    build_disposal_method_classification_observation,
    build_disposal_net_value_recalculation_observation,
    build_disposal_other_reduction_tt_observation,
    build_disposal_reconciliation_formula_source_observation,
    build_disposal_reconciliation_readability_observation,
    build_disposal_replacement_reason_observation,
    build_disposal_required_fields_observation,
    build_disposal_rollforward_reconciliation_observation,
    build_disposal_sample_match_observation,
    build_disposal_sample_pool_observation,
    build_disposal_sampling_te_cra_observation,
    build_disposal_sale_evidence_observation,
    build_disposal_test_amount_recalculation_observation,
    build_disposal_test_attributes_observation,
)
from rules.disposal_reconciliation import RULE_IDS as DISPOSAL_RECONCILIATION_RULE_IDS
from rules.disposal_reconciliation import run_disposal_reconciliation_rules
from rules.disposal_sampling_output import RULE_IDS as DISPOSAL_SAMPLING_RULE_IDS
from rules.disposal_sampling_output import run_disposal_sampling_rules
from rules.execution_recorder import RuleExecutionRecorder
from rules.models import ColumnContext, QcIssue
from rules.readiness import evaluate_rule_readiness, readiness_spec_from_registry
from rules.registry import get_by_rule_id

DISPOSAL_RULE_IDS: tuple[str, ...] = (
    "disposal_sample_match",
    *DISPOSAL_RECONCILIATION_RULE_IDS,
    *DISPOSAL_LIST_RULE_IDS,
    *DISPOSAL_SAMPLING_RULE_IDS,
    *DISPOSAL_DETAILED_RULE_IDS,
)


def _execute_disposal_list_rule(
    recorder: RuleExecutionRecorder,
    rule_id: str,
    ctx: ColumnContext,
    function,
    *args,
) -> list[QcIssue]:
    spec = get_by_rule_id(rule_id)
    if spec is None:
        raise ValueError(f"Rule is not registered: {rule_id}")
    decision = evaluate_rule_readiness(readiness_spec_from_registry(spec), ctx)
    if not decision.ready:
        recorder.record_data_insufficient(rule_id, decision.note())
        return []
    return recorder.execute_rule(rule_id, function, *args)


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
        if disposal_list is None:
            list_issues = run_disposal_list_rules(
                disposal_list,
                disposal_list_summary,
                lead=lead,
                recorder=recorder,
            )
        else:
            list_ctx = ColumnContext(
                mapped_fields={m.standard_field for m in disposal_list.mapped_fields},
                mapped_headers={m.standard_field: m.source_header for m in disposal_list.mapped_fields},
                mapped_columns={m.standard_field: m.column_index for m in disposal_list.mapped_fields},
                field_resolutions=disposal_list.field_resolutions,
                source_sheet=disposal_list.source_sheet,
                procedure_code="K.02.2",
            )
            list_issues = []
            list_issues.extend(
                _execute_disposal_list_rule(
                    recorder,
                    "disposal_required_fields",
                    list_ctx,
                    check_disposal_required_fields,
                    disposal_list,
                )
            )
            list_issues.extend(
                _execute_disposal_list_rule(
                    recorder,
                    "disposal_list_net_value_recalculation",
                    list_ctx,
                    check_disposal_list_net_values,
                    disposal_list,
                )
            )
            list_issues.extend(
                _execute_disposal_list_rule(
                    recorder,
                    "disposal_method_classification",
                    list_ctx,
                    check_disposal_method_classification,
                    disposal_list_summary,
                )
            )
            list_issues.extend(
                _execute_disposal_list_rule(
                    recorder,
                    "disposal_other_reduction_over_tt",
                    list_ctx,
                    check_disposal_other_reduction_over_tt,
                    disposal_list_summary,
                    lead,
                )
            )
        _record_disposal_list_observations(
            recorder,
            disposal_list=disposal_list,
            disposal_list_summary=disposal_list_summary,
            lead=lead,
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
            disposal_test=disposal_test,
            disposal_sample_output=disposal_sample_output,
            lead=lead,
            issues=sampling_issues,
        )
        issues.extend(sampling_issues)
        detailed_issues = run_disposal_detailed_test_rules(disposal_test, recorder=recorder)
        _record_disposal_detailed_observations(
            recorder,
            disposal_test=disposal_test,
            issues=detailed_issues,
        )
        issues.extend(detailed_issues)
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
    _record_if_present(
        recorder,
        "disposal_difference_investigation",
        build_disposal_difference_investigation_observation(
            disposal_test,
            lead,
            _issues_for(issues, "disposal_difference_investigation"),
        ),
    )


def _record_disposal_list_observations(
    recorder: RuleExecutionRecorder,
    *,
    disposal_list: FaListDataset | None,
    disposal_list_summary: DisposalListSummary | None,
    lead: LeadSheetDataset | None,
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
    _record_if_present(
        recorder,
        "disposal_method_classification",
        build_disposal_method_classification_observation(
            disposal_list_summary,
            issues=_issues_for(issues, "disposal_method_classification"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_other_reduction_over_tt",
        build_disposal_other_reduction_tt_observation(
            disposal_list_summary,
            lead,
            _issues_for(issues, "disposal_other_reduction_over_tt"),
        ),
    )


def _record_disposal_sampling_observations(
    recorder: RuleExecutionRecorder,
    *,
    disposal_list_summary: DisposalListSummary | None,
    disposal_test: DisposalTestSheetDataset | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
    lead: LeadSheetDataset | None,
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
    _record_if_present(
        recorder,
        "disposal_sampling_te_cra_consistency",
        build_disposal_sampling_te_cra_observation(
            disposal_sample_output,
            lead,
            _issues_for(issues, "disposal_sampling_te_cra_consistency"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_sample_replacement_reason",
        build_disposal_replacement_reason_observation(
            disposal_test,
            _issues_for(issues, "disposal_sample_replacement_reason"),
        ),
    )


def _record_disposal_detailed_observations(
    recorder: RuleExecutionRecorder,
    *,
    disposal_test: DisposalTestSheetDataset | None,
    issues: list[QcIssue],
) -> None:
    _record_if_present(
        recorder,
        "disposal_test_attributes_complete",
        build_disposal_test_attributes_observation(
            disposal_test,
            _issues_for(issues, "disposal_test_attributes_complete"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_test_amount_recalculation",
        build_disposal_test_amount_recalculation_observation(
            disposal_test,
            _issues_for(issues, "disposal_test_amount_recalculation"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_sale_evidence_complete",
        build_disposal_sale_evidence_observation(
            disposal_test,
            _issues_for(issues, "disposal_sale_evidence_complete"),
        ),
    )
    _record_if_present(
        recorder,
        "disposal_exception_followup",
        build_disposal_exception_followup_observation(
            disposal_test,
            _issues_for(issues, "disposal_exception_followup"),
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
