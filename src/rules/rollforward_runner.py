from __future__ import annotations

from ingest.reconciliation import ReconciliationCheck
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.models import QcIssue
from rules.rollforward_abnormal_amounts import check_rollforward_abnormal_amounts
from rules.rollforward_columns_complete import check_rollforward_columns_complete
from rules.rollforward_exists import check_rollforward_exists
from rules.rollforward_fa_list_reconciliation import check_rollforward_fa_list_reconciliation

ROLLFORWARD_RULE_IDS: tuple[str, ...] = (
    "rollforward_exists",
    "rollforward_columns_complete",
    "rollforward_abnormal_amounts",
    "rollforward_fa_list_reconciliation",
)


def run_rollforward_rules(
    rollforward: RollforwardSheetDataset | None,
    *,
    reconciliations: list[ReconciliationCheck] | None = None,
) -> list[QcIssue]:
    """执行 K.01 后推 P0 规则（不含 attach_rule_metadata）。"""
    issues: list[QcIssue] = []
    issues.extend(check_rollforward_exists(rollforward))
    issues.extend(check_rollforward_columns_complete(rollforward))
    issues.extend(check_rollforward_abnormal_amounts(rollforward))
    issues.extend(
        check_rollforward_fa_list_reconciliation(
            reconciliations,
            rollforward=rollforward,
        )
    )
    return issues
