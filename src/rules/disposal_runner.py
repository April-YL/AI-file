from __future__ import annotations

from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalSampleOutputDataset,
    DisposalTestSheetDataset,
)
from rules.disposal_consistency import check_disposal_sample_match
from rules.models import QcIssue

DISPOSAL_RULE_IDS: tuple[str, ...] = ("disposal_sample_match",)


def run_disposal_rules(
    *,
    disposal_test: DisposalTestSheetDataset | None = None,
    disposal_sample_output: DisposalSampleOutputDataset | None = None,
    disposal_execution_path: DisposalExecutionPathDataset | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    issues.extend(
        check_disposal_sample_match(
            disposal_test,
            disposal_sample_output,
            execution_path=disposal_execution_path,
        )
    )
    return issues
