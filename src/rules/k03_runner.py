from __future__ import annotations

from ingest.k03_sheet import (
    EXECUTION_PATH_POLICY_REVIEW,
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_TOD_SAMPLING,
    K03SheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.k03_observations import (
    K03_LOW_RISK_HOW_RULE_IDS,
    build_k03_missing_dataset_observation,
)
from rules.k03_policy_review import RULE_IDS as K03_POLICY_REVIEW_RULE_IDS
from rules.k03_policy_review import run_k03_policy_review_rules
from rules.k03_sap import RULE_IDS as K03_SAP_RULE_IDS
from rules.k03_sap import run_k03_sap_rules
from rules.k03_tod_sampling import RULE_IDS as K03_TOD_SAMPLING_RULE_IDS
from rules.k03_tod_sampling import run_k03_tod_sampling_rules
from rules.k03_tod_by_item import RULE_IDS as K03_TOD_BY_ITEM_RULE_IDS
from rules.k03_tod_by_item import run_k03_tod_by_item_rules
from rules.models import QcIssue

K03_RULE_IDS: tuple[str, ...] = (
    *K03_SAP_RULE_IDS,
    *K03_TOD_SAMPLING_RULE_IDS,
    *K03_TOD_BY_ITEM_RULE_IDS,
    *K03_POLICY_REVIEW_RULE_IDS,
)


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
        note = "未识别 K.03 折旧测试或折旧政策复核工作表"
        for rule_id in K03_RULE_IDS:
            recorder.record_data_insufficient(rule_id, note)
            _attach_missing_observation(recorder, rule_id, note)
        return issues
    sap_seen = False
    for dataset in datasets:
        if dataset.execution_path in {EXECUTION_PATH_SAP_MEDIUM, EXECUTION_PATH_SAP_HIGH}:
            sap_seen = True
            issues.extend(
                run_k03_sap_rules(
                    dataset,
                    lead=lead,
                    k03_sheets=datasets,
                    recorder=recorder,
                )
            )
        issues.extend(
            run_k03_tod_by_item_rules(
                dataset,
                lead=lead,
                rollforward=rollforward,
                recorder=recorder,
            )
        )
    if not sap_seen:
        note = "未识别到 K.03.1 SAP 执行路径；当前底稿可能采用 TOD 或政策复核路径"
        for rule_id in K03_SAP_RULE_IDS:
            recorder.record_not_applicable(rule_id, note)
            _attach_path_not_applicable_observation(recorder, rule_id, datasets[0], note)

    tod_sampling_dataset = next(
        (
            dataset
            for dataset in datasets
            if dataset.execution_path == EXECUTION_PATH_TOD_SAMPLING
            and dataset.template_type == "tod_sampling"
        ),
        None,
    )
    tod_sampling_output = next(
        (
            dataset
            for dataset in datasets
            if dataset.execution_path == EXECUTION_PATH_TOD_SAMPLING
            and dataset.template_type == "tod_sampling_output"
        ),
        None,
    )
    if tod_sampling_dataset is not None:
        issues.extend(
            run_k03_tod_sampling_rules(
                tod_sampling_dataset,
                sample_output=tod_sampling_output,
                lead=lead,
                rollforward=rollforward,
                recorder=recorder,
            )
        )
    elif tod_sampling_output is not None:
        issues.extend(
            run_k03_tod_sampling_rules(
                None,
                sample_output=tod_sampling_output,
                lead=lead,
                rollforward=rollforward,
                recorder=recorder,
            )
        )
    else:
        note = "未识别到 K.03.2 TOD 抽样执行路径；当前底稿可能采用 SAP 或 by-item 方式"
        for rule_id in K03_TOD_SAMPLING_RULE_IDS:
            recorder.record_not_applicable(rule_id, note)
            _attach_path_not_applicable_observation(recorder, rule_id, datasets[0], note)

    policy_dataset = next(
        (dataset for dataset in datasets if dataset.execution_path == EXECUTION_PATH_POLICY_REVIEW),
        None,
    )
    if policy_dataset is not None:
        issues.extend(run_k03_policy_review_rules(policy_dataset, fa_list=fa_list, recorder=recorder))
    else:
        note = "未识别 K.03.3 折旧政策复核执行路径"
        for rule_id in K03_POLICY_REVIEW_RULE_IDS:
            recorder.record_data_insufficient(rule_id, note)
            _attach_missing_observation(recorder, rule_id, note)
    return issues


def _attach_missing_observation(
    recorder: RuleExecutionRecorder,
    rule_id: str,
    note: str,
) -> None:
    if rule_id not in K03_LOW_RISK_HOW_RULE_IDS:
        return
    recorder.record_observation(
        rule_id,
        build_k03_missing_dataset_observation(rule_id, reason=note),
    )


def _attach_path_not_applicable_observation(
    recorder: RuleExecutionRecorder,
    rule_id: str,
    dataset: K03SheetDataset,
    note: str,
) -> None:
    recorder.record_observation(
        rule_id,
        {
            "checked_data": [
                {
                    "sheet": dataset.sheet_name,
                    "section": "K.03 执行路径识别",
                    "location": None,
                    "identified_by": {
                        "sheet_name": dataset.sheet_name,
                        "section": "K.03 执行路径识别",
                        "matched_keywords": [dataset.sheet_name, dataset.execution_path],
                        "matched_rows": [],
                        "matched_columns": [],
                    },
                    "key_columns": ["execution_path"],
                    "values_read": [
                        {
                            "label": "识别到的执行路径",
                            "value": dataset.execution_path,
                            "row": None,
                            "column": None,
                            "cell": None,
                            "unit": None,
                            "amount_type": "execution_path",
                        }
                    ],
                    "missing_data": [note],
                }
            ],
            "check_logic": "系统先识别 K.03 工作表执行路径；当当前底稿未采用该规则对应路径时，记录为不适用。",
            "expected_result": "只有识别到对应 K.03 执行路径时，才执行该规则。",
            "actual_result": f"本次规则不适用：{note}",
            "result_summary": "不适用，未触发 finding。",
        },
    )
