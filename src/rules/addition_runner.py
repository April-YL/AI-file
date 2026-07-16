from __future__ import annotations

from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.models import SheetKind
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.addition_consistency import check_addition_sample_match
from rules.addition_observations import (
    build_addition_assertions_observation,
    build_addition_data_insufficient_observation,
    build_addition_population_homogeneity_observation,
    build_addition_replacement_reason_observation,
    build_addition_required_fields_observation,
    build_addition_rollforward_reconciliation_observation,
    build_addition_sample_match_evidence_observation,
    build_addition_sample_pool_observation,
    build_addition_te_cra_observation,
)
from rules.addition_population_homogeneity import check_addition_population_homogeneity
from rules.addition_required_fields import check_addition_required_fields
from rules.addition_rollforward_reconciliation import check_addition_rollforward_reconciliation
from rules.addition_sampling_output import (
    check_addition_sample_pool_purchase_amount_match,
    check_addition_sample_replacement_reason,
    check_addition_sampling_assertions_scope,
    check_addition_sampling_te_cra_consistency,
)
from rules.execution_recorder import RuleExecutionRecorder
from rules.list_readiness_context import build_list_column_context
from rules.models import ColumnContext, QcIssue
from rules.readiness import evaluate_rule_readiness, readiness_spec_from_registry
from rules.registry import get_by_rule_id

ADDITION_RULE_IDS: tuple[str, ...] = (
    "addition_required_fields",
    "addition_population_homogeneity",
    "addition_rollforward_reconciliation",
    "addition_sample_match",
    "addition_sample_pool_purchase_amount_match",
    "addition_sampling_te_cra_consistency",
    "addition_sampling_assertions_scope",
    "addition_sample_replacement_reason",
)


def _readiness(rule_id: str, ctx: ColumnContext):
    spec = get_by_rule_id(rule_id)
    if spec is None:
        raise ValueError(f"Rule is not registered: {rule_id}")
    return evaluate_rule_readiness(readiness_spec_from_registry(spec), ctx)


def _record_readiness_insufficient(recorder: RuleExecutionRecorder, decision) -> None:
    reason = decision.note()
    recorder.record_data_insufficient(decision.rule_id, reason)
    recorder.record_observation(
        decision.rule_id,
        build_addition_data_insufficient_observation(decision.rule_id, reason),
    )


def run_addition_rules(
    addition_list: FaListDataset | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
    addition_test: AdditionTestSheetDataset | None = None,
    addition_sample_output: AdditionSampleOutputDataset | None = None,
    addition_execution_path: AdditionExecutionPathDataset | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues: list[QcIssue] = []
    if addition_list is None:
        reason = "未识别新增清单，无法执行新增清单相关检查"
        for rule_id in (
            "addition_required_fields",
            "addition_population_homogeneity",
            "addition_rollforward_reconciliation",
        ):
            recorder.record_data_insufficient(rule_id, reason)
            recorder.record_observation(
                rule_id,
                build_addition_data_insufficient_observation(rule_id, reason),
            )
    if addition_list is not None:
        available_data = {"addition_list"}
        if rollforward is not None:
            available_data.add("rollforward")
        if lead is not None:
            available_data.add("lead")
        if addition_test is not None:
            available_data.add("addition_test")
        if addition_sample_output is not None:
            available_data.add("addition_sample_output")
        ctx = build_list_column_context(
            addition_list,
            expected_kind=SheetKind.ADDITION_LIST,
            procedure_code="K.02.1",
            available_data=available_data,
        )
        required_decision = _readiness("addition_required_fields", ctx)
        if required_decision.ready:
            required_issues = recorder.execute_rule(
                "addition_required_fields",
                check_addition_required_fields,
                addition_list.records,
                ctx,
            )
            recorder.record_observation(
                "addition_required_fields",
                build_addition_required_fields_observation(addition_list, ctx, required_issues),
            )
            issues.extend(required_issues)
        else:
            _record_readiness_insufficient(recorder, required_decision)

        homogeneity_decision = _readiness("addition_population_homogeneity", ctx)
        if homogeneity_decision.ready:
            homogeneity_issues = recorder.execute_rule(
                "addition_population_homogeneity",
                check_addition_population_homogeneity,
                addition_list.records,
                ctx,
            )
            recorder.record_observation(
                "addition_population_homogeneity",
                build_addition_population_homogeneity_observation(addition_list, ctx, homogeneity_issues),
            )
            issues.extend(homogeneity_issues)
        else:
            _record_readiness_insufficient(recorder, homogeneity_decision)

        reconciliation_decision = _readiness("addition_rollforward_reconciliation", ctx)
        if reconciliation_decision.ready:
            reconciliation_issues = recorder.execute_rule(
                "addition_rollforward_reconciliation",
                check_addition_rollforward_reconciliation,
                addition_list,
                rollforward=rollforward,
                lead=lead,
                addition_test=addition_test,
            )
            recorder.record_observation(
                "addition_rollforward_reconciliation",
                build_addition_rollforward_reconciliation_observation(
                    addition_list,
                    rollforward,
                    lead,
                    addition_test,
                    reconciliation_issues,
                ),
            )
            issues.extend(reconciliation_issues)
        else:
            _record_readiness_insufficient(recorder, reconciliation_decision)
    sample_match_issues = recorder.execute_rule(
        "addition_sample_match",
        check_addition_sample_match,
        addition_test,
        addition_sample_output,
        execution_path=addition_execution_path,
    )
    recorder.record_observation(
        "addition_sample_match",
        build_addition_sample_match_evidence_observation(
            addition_test,
            addition_sample_output,
            addition_execution_path,
            sample_match_issues,
        ),
    )
    issues.extend(sample_match_issues)
    if _is_addition_sampling_skipped(addition_execution_path):
        for rule_id in (
            "addition_sample_pool_purchase_amount_match",
            "addition_sampling_te_cra_consistency",
            "addition_sampling_assertions_scope",
            "addition_sample_replacement_reason",
        ):
            recorder.record_not_applicable(rule_id, "新增测试已豁免或测试表注明不执行")
        return issues
    sample_pool_decision = _readiness(
        "addition_sample_pool_purchase_amount_match",
        ctx if addition_list is not None else None,
    )
    if sample_pool_decision.ready:
        sample_pool_issues = recorder.execute_rule(
            "addition_sample_pool_purchase_amount_match",
            check_addition_sample_pool_purchase_amount_match,
            addition_list,
            addition_sample_output,
            rollforward=rollforward,
            addition_test=addition_test,
        )
    else:
        _record_readiness_insufficient(recorder, sample_pool_decision)
        sample_pool_issues = []
    recorder.record_observation(
        "addition_sample_pool_purchase_amount_match",
        build_addition_sample_pool_observation(
            addition_list,
            addition_sample_output,
            rollforward,
            addition_test,
            sample_pool_issues,
        ),
    )
    issues.extend(sample_pool_issues)
    te_cra_issues = recorder.execute_rule(
        "addition_sampling_te_cra_consistency",
        check_addition_sampling_te_cra_consistency,
        addition_sample_output,
        lead,
    )
    recorder.record_observation(
        "addition_sampling_te_cra_consistency",
        build_addition_te_cra_observation(addition_sample_output, lead, te_cra_issues),
    )
    issues.extend(te_cra_issues)
    assertions_issues = recorder.execute_rule(
        "addition_sampling_assertions_scope",
        check_addition_sampling_assertions_scope,
        addition_sample_output,
    )
    recorder.record_observation(
        "addition_sampling_assertions_scope",
        build_addition_assertions_observation(addition_sample_output, assertions_issues),
    )
    issues.extend(assertions_issues)
    replacement_issues = recorder.execute_rule(
        "addition_sample_replacement_reason",
        check_addition_sample_replacement_reason,
        addition_test,
    )
    recorder.record_observation(
        "addition_sample_replacement_reason",
        build_addition_replacement_reason_observation(addition_test, replacement_issues),
    )
    issues.extend(replacement_issues)
    return issues


def _is_addition_sampling_skipped(
    addition_execution_path: AdditionExecutionPathDataset | None,
) -> bool:
    if addition_execution_path is None:
        return False
    return addition_execution_path.path_kind in {"summary_waived", "test_sheet_waiver_note"}
