from __future__ import annotations

from ingest.k03_sheet import EXECUTION_PATH_POLICY_REVIEW, K03SheetDataset
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.k03_policy_review import RULE_IDS as K03_POLICY_REVIEW_RULE_IDS
from rules.k03_policy_review import run_k03_policy_review_rules
from rules.k03_tod_by_item import RULE_IDS as K03_TOD_BY_ITEM_RULE_IDS
from rules.k03_tod_by_item import run_k03_tod_by_item_rules
from rules.models import QcIssue

K03_RULE_IDS: tuple[str, ...] = (*K03_TOD_BY_ITEM_RULE_IDS, *K03_POLICY_REVIEW_RULE_IDS)


def run_k03_rules(
    k03_sheets: list[K03SheetDataset] | None,
    *,
    lead: LeadSheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
    fa_list: FaListDataset | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    datasets = k03_sheets or []
    for dataset in datasets:
        issues.extend(
            run_k03_tod_by_item_rules(
                dataset,
                lead=lead,
                rollforward=rollforward,
            )
        )

    policy_dataset = next(
        (dataset for dataset in datasets if dataset.execution_path == EXECUTION_PATH_POLICY_REVIEW),
        None,
    )
    if policy_dataset is not None:
        issues.extend(run_k03_policy_review_rules(policy_dataset, fa_list=fa_list))
    return issues
