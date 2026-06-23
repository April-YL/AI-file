from __future__ import annotations

from ingest.k03_sheet import EXECUTION_PATH_POLICY_REVIEW, K03SheetDataset
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
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
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues: list[QcIssue] = []
    datasets = k03_sheets or []
    if not datasets:
        for rule_id in K03_RULE_IDS:
            recorder.record_data_insufficient(rule_id, "未识别 K.03 折旧测试或折旧政策复核工作表")
        return issues
    for dataset in datasets:
        issues.extend(
            run_k03_tod_by_item_rules(
                dataset,
                lead=lead,
                rollforward=rollforward,
                recorder=recorder,
            )
        )

    policy_dataset = next(
        (dataset for dataset in datasets if dataset.execution_path == EXECUTION_PATH_POLICY_REVIEW),
        None,
    )
    if policy_dataset is not None:
        issues.extend(run_k03_policy_review_rules(policy_dataset, fa_list=fa_list, recorder=recorder))
    else:
        for rule_id in K03_POLICY_REVIEW_RULE_IDS:
            recorder.record_data_insufficient(rule_id, "未识别 K.03.3 折旧政策复核执行路径")
    return issues
