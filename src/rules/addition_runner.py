from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
)
from rules.addition_consistency import check_addition_sample_match
from rules.addition_population_homogeneity import check_addition_population_homogeneity
from rules.addition_required_fields import check_addition_required_fields
from rules.addition_rollforward_reconciliation import check_addition_rollforward_reconciliation
from rules.addition_sampling_output import (
    check_addition_sample_pool_purchase_amount_match,
    check_addition_sample_replacement_reason,
    check_addition_sampling_assertions_scope,
    check_addition_sampling_te_cra_consistency,
)
from rules.models import ColumnContext, QcIssue

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


def run_addition_rules(
    addition_list: FaListDataset | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
    addition_test: AdditionTestSheetDataset | None = None,
    addition_sample_output: AdditionSampleOutputDataset | None = None,
    addition_execution_path: AdditionExecutionPathDataset | None = None,
) -> list[QcIssue]:
    """执行 K.02.1 新增清单基础规则（不含 attach_rule_metadata）。"""
    if addition_list is None:
        issues: list[QcIssue] = []
    else:
        ctx = ColumnContext(
            mapped_fields={m.standard_field for m in addition_list.mapped_fields},
            source_sheet=addition_list.source_sheet,
            procedure_code="K.02.1",
        )
        issues = []
        issues.extend(check_addition_required_fields(addition_list.records, ctx))
        issues.extend(check_addition_population_homogeneity(addition_list.records, ctx))
        issues.extend(
            check_addition_rollforward_reconciliation(
                addition_list,
                rollforward=rollforward,
                lead=lead,
            )
        )
    issues.extend(
        check_addition_sample_match(
            addition_test,
            addition_sample_output,
            execution_path=addition_execution_path,
        )
    )
    if _is_addition_sampling_skipped(addition_execution_path):
        return issues
    issues.extend(
        check_addition_sample_pool_purchase_amount_match(addition_list, addition_sample_output)
    )
    issues.extend(check_addition_sampling_te_cra_consistency(addition_sample_output, lead))
    issues.extend(check_addition_sampling_assertions_scope(addition_sample_output))
    issues.extend(check_addition_sample_replacement_reason(addition_test))
    return issues


def _is_addition_sampling_skipped(
    addition_execution_path: AdditionExecutionPathDataset | None,
) -> bool:
    if addition_execution_path is None:
        return False
    return addition_execution_path.path_kind in {"summary_waived", "test_sheet_waiver_note"}
