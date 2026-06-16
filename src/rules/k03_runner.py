from __future__ import annotations

from ingest.k03_sheet import K03SheetDataset
from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.k03_tod_by_item import RULE_IDS as K03_TOD_BY_ITEM_RULE_IDS
from rules.k03_tod_by_item import run_k03_tod_by_item_rules
from rules.models import QcIssue

K03_RULE_IDS: tuple[str, ...] = (*K03_TOD_BY_ITEM_RULE_IDS,)


def run_k03_rules(
    k03_sheets: list[K03SheetDataset] | None,
    *,
    lead: LeadSheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    for dataset in k03_sheets or []:
        issues.extend(
            run_k03_tod_by_item_rules(
                dataset,
                lead=lead,
                rollforward=rollforward,
            )
        )
    return issues
