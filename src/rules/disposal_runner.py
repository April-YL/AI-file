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
    issues.extend(
        run_disposal_reconciliation_rules(
            disposal_list_summary=disposal_list_summary,
            disposal_test=disposal_test,
            disposal_execution_path=disposal_execution_path,
            rollforward=rollforward,
            lead=lead,
            recorder=recorder,
        )
    )
    if not disposal_execution_path or disposal_execution_path.path_kind != "summary_waived":
        issues.extend(
            run_disposal_list_rules(
                disposal_list,
                disposal_list_summary,
                lead=lead,
                recorder=recorder,
            )
        )
    else:
        for rule_id in DISPOSAL_LIST_RULE_IDS:
            recorder.record_not_applicable(rule_id, "处置测试已豁免，处置清单检查暂不适用")
    if not disposal_execution_path or disposal_execution_path.path_kind not in {
        "summary_waived",
        "test_sheet_waiver_note",
    }:
        issues.extend(
            run_disposal_sampling_rules(
                disposal_list_summary=disposal_list_summary,
                disposal_test=disposal_test,
                disposal_sample_output=disposal_sample_output,
                lead=lead,
                recorder=recorder,
            )
        )
        issues.extend(run_disposal_detailed_test_rules(disposal_test, recorder=recorder))
    else:
        for rule_id in (*DISPOSAL_SAMPLING_RULE_IDS, *DISPOSAL_DETAILED_RULE_IDS):
            recorder.record_not_applicable(rule_id, "处置测试已豁免或测试表注明不执行")
    issues.extend(
        recorder.execute_rule(
            "disposal_sample_match",
            check_disposal_sample_match,
            disposal_test,
            disposal_sample_output,
            execution_path=disposal_execution_path,
        )
    )
    return issues
