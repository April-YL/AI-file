from __future__ import annotations

from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.addition_population_homogeneity import check_addition_population_homogeneity
from rules.addition_required_fields import check_addition_required_fields
from rules.addition_rollforward_reconciliation import check_addition_rollforward_reconciliation
from rules.models import ColumnContext, QcIssue

ADDITION_RULE_IDS: tuple[str, ...] = (
    "addition_required_fields",
    "addition_population_homogeneity",
    "addition_rollforward_reconciliation",
)


def run_addition_rules(
    addition_list: FaListDataset | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
) -> list[QcIssue]:
    """执行 K.02.1 新增清单基础规则（不含 attach_rule_metadata）。"""
    if addition_list is None:
        return []
    ctx = ColumnContext(
        mapped_fields={m.standard_field for m in addition_list.mapped_fields},
        source_sheet=addition_list.source_sheet,
        procedure_code="K.02.1",
    )
    issues: list[QcIssue] = []
    issues.extend(check_addition_required_fields(addition_list.records, ctx))
    issues.extend(check_addition_population_homogeneity(addition_list.records, ctx))
    issues.extend(
        check_addition_rollforward_reconciliation(
            addition_list,
            rollforward=rollforward,
            lead=lead,
        )
    )
    return issues
