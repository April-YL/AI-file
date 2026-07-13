from __future__ import annotations

from ingest.k03_sheet import (
    COMPONENT_STATE_AMBIGUOUS,
    COMPONENT_STATE_EXECUTED,
    COMPONENT_STATE_INCOMPLETE,
    EXECUTION_PATH_POLICY_REVIEW,
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING,
    EXECUTION_PATH_TOD_BY_ITEM,
    EXECUTION_PATH_TOD_SAMPLING,
    EXECUTION_PATH_UNKNOWN,
    K03ComponentSheet,
    K03ExecutionProfile,
    K03SheetDataset,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from ingest.summary_sheet import SummarySheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.k03_execution_control import RULE_IDS as K03_EXECUTION_CONTROL_RULE_IDS
from rules.k03_execution_control import run_k03_execution_control
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

K03_COMPONENT_RULE_IDS: tuple[str, ...] = (
    *K03_SAP_RULE_IDS,
    *K03_TOD_SAMPLING_RULE_IDS,
    *K03_TOD_BY_ITEM_RULE_IDS,
    *K03_POLICY_REVIEW_RULE_IDS,
)
K03_RULE_IDS: tuple[str, ...] = (*K03_EXECUTION_CONTROL_RULE_IDS, *K03_COMPONENT_RULE_IDS)


def run_k03_rules(
    k03_sheets: list[K03SheetDataset] | None,
    *,
    lead: LeadSheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
    fa_list: FaListDataset | None = None,
    k03_execution_profile: K03ExecutionProfile | None = None,
    summary: SummarySheetDataset | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues = run_k03_execution_control(summary, k03_execution_profile, recorder=recorder)
    if k03_execution_profile is not None:
        issues.extend(_run_k03_rules_from_profile(
            k03_sheets or [],
            k03_execution_profile,
            lead=lead,
            rollforward=rollforward,
            fa_list=fa_list,
            recorder=recorder,
        ))
        return issues

    datasets = k03_sheets or []
    if not datasets:
        note = "未识别 K.03 折旧测试或折旧政策复核工作表"
        for rule_id in K03_COMPONENT_RULE_IDS:
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


def _run_k03_rules_from_profile(
    datasets: list[K03SheetDataset],
    profile: K03ExecutionProfile,
    *,
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
    fa_list: FaListDataset | None,
    recorder: RuleExecutionRecorder,
) -> list[QcIssue]:
    """Route existing K.03 rules using workbook-level ingest recognition."""
    issues: list[QcIssue] = []
    representative = datasets[0] if datasets else None
    executed_paths = set(profile.executed_depreciation_paths)
    has_depreciation_components = any(
        profile.component_sheets.get(role)
        for role in ("sap_medium", "sap_high", "tod_by_item", "tod_sampling", "tod_sampling_output", "unknown_depreciation_test")
    )

    sap_components = _components_with_states(
        profile, ("sap_medium", "sap_high"), {COMPONENT_STATE_EXECUTED}
    )
    if sap_components:
        for component in sap_components:
            sap_dataset = _match_component_dataset(component, datasets)
            if sap_dataset is None:
                continue
            component_recorder = RuleExecutionRecorder()
            issues.extend(
                run_k03_sap_rules(
                    sap_dataset,
                    lead=lead,
                    k03_sheets=datasets,
                    k03_execution_profile=profile,
                    recorder=component_recorder,
                )
            )
            _merge_component_ledger(recorder, component_recorder)
    elif _has_incomplete_component(profile, ("sap_medium", "sap_high")):
        _record_group_data_insufficient(
            recorder,
            K03_SAP_RULE_IDS,
            "K.03 SAP sheet contains project data but is incomplete or ambiguous.",
        )
    elif has_depreciation_components or executed_paths:
        _record_group_not_applicable(
            recorder,
            K03_SAP_RULE_IDS,
            representative,
            "The workpaper did not execute an SAP depreciation-test path.",
        )
    else:
        _record_group_data_insufficient(recorder, K03_SAP_RULE_IDS, "K.03 depreciation test method was not identified.")

    by_item_components = _components_with_states(
        profile, ("tod_by_item",), {COMPONENT_STATE_EXECUTED}
    )
    if by_item_components:
        for component in by_item_components:
            by_item_dataset = _match_component_dataset(component, datasets)
            if by_item_dataset is None:
                continue
            issues.extend(
                run_k03_tod_by_item_rules(
                    by_item_dataset,
                    lead=lead,
                    rollforward=rollforward,
                    recorder=recorder,
                )
            )
    elif _has_incomplete_component(profile, ("tod_by_item",)):
        _record_group_data_insufficient(
            recorder,
            K03_TOD_BY_ITEM_RULE_IDS,
            "K.03 TOD by-item sheet contains project data but is incomplete or ambiguous.",
        )
    elif has_depreciation_components or executed_paths:
        _record_group_not_applicable(
            recorder,
            K03_TOD_BY_ITEM_RULE_IDS,
            representative,
            "The workpaper did not execute a TOD by-item depreciation-test path.",
        )
    else:
        _record_group_data_insufficient(recorder, K03_TOD_BY_ITEM_RULE_IDS, "K.03 depreciation test method was not identified.")

    sampling_components = _components_with_states(
        profile, ("tod_sampling",), {COMPONENT_STATE_EXECUTED}
    )
    if sampling_components:
        sampling_output = _first_component_dataset(profile, datasets, ("tod_sampling_output",))
        for component in sampling_components:
            sampling_dataset = _match_component_dataset(component, datasets)
            if sampling_dataset is None:
                continue
            issues.extend(
                run_k03_tod_sampling_rules(
                    sampling_dataset,
                    sample_output=sampling_output,
                    lead=lead,
                    rollforward=rollforward,
                    recorder=recorder,
                )
            )
    elif _has_incomplete_component(profile, ("tod_sampling", "tod_sampling_output")):
        _record_group_data_insufficient(
            recorder,
            K03_TOD_SAMPLING_RULE_IDS,
            "K.03 TOD sampling sheet or sample output contains project data but is incomplete or ambiguous.",
        )
    elif has_depreciation_components or executed_paths:
        _record_group_not_applicable(
            recorder,
            K03_TOD_SAMPLING_RULE_IDS,
            representative,
            "The workpaper did not execute a TOD sampling depreciation-test path.",
        )
    else:
        _record_group_data_insufficient(recorder, K03_TOD_SAMPLING_RULE_IDS, "K.03 depreciation test method was not identified.")

    policy_component = next(iter(_components_with_states(
        profile, ("policy_review",), {COMPONENT_STATE_EXECUTED}
    )), None)
    policy_dataset = _match_component_dataset(policy_component, datasets) if policy_component else None
    if policy_dataset is not None:
        issues.extend(run_k03_policy_review_rules(policy_dataset, fa_list=fa_list, recorder=recorder))
    elif _has_incomplete_component(profile, ("policy_review",)):
        _record_group_data_insufficient(
            recorder,
            K03_POLICY_REVIEW_RULE_IDS,
            "K.03.3 depreciation policy review contains project data but is incomplete or ambiguous.",
        )
    else:
        _record_group_data_insufficient(
            recorder, K03_POLICY_REVIEW_RULE_IDS,
            "K.03.3 depreciation policy review sheet was not executed or was not identified.",
        )
    return issues


def _merge_component_ledger(
    recorder: RuleExecutionRecorder,
    component_recorder: RuleExecutionRecorder,
) -> None:
    """Merge one K.03 component run without losing evidence from earlier sheets."""
    existing_items = {
        item["rule_id"]: item for item in recorder.to_ledger().get("items", [])
    }
    for item in component_recorder.to_ledger().get("items", []):
        rule_id = item["rule_id"]
        observation = _merge_observations(
            existing_items.get(rule_id, {}).get("observation"),
            item.get("observation"),
        )
        status = item["status"]
        if status == "EXECUTED":
            recorder.record_executed(
                rule_id,
                item.get("finding_count", 0),
                note=item.get("status_note", ""),
                observation=observation,
            )
        elif status == "DATA_INSUFFICIENT":
            recorder.record_data_insufficient(rule_id, item.get("status_note", ""))
            recorder.record_observation(rule_id, observation)
        else:
            recorder.record_not_applicable(rule_id, item.get("status_note", ""))
            recorder.record_observation(rule_id, observation)
        existing_items = {
            row["rule_id"]: row for row in recorder.to_ledger().get("items", [])
        }


def _merge_observations(
    existing: dict | None,
    current: dict | None,
) -> dict | None:
    if existing is None:
        return current
    if current is None:
        return existing
    merged = dict(current)
    merged["checked_data"] = [
        *existing.get("checked_data", []),
        *current.get("checked_data", []),
    ]
    merged["actual_result"] = "；".join(
        text
        for text in (existing.get("actual_result"), current.get("actual_result"))
        if text
    )
    merged["result_summary"] = "；".join(
        text
        for text in (existing.get("result_summary"), current.get("result_summary"))
        if text
    )
    return merged


def _components_with_states(
    profile: K03ExecutionProfile,
    roles: tuple[str, ...],
    states: set[str],
) -> list[K03ComponentSheet]:
    return [
        component
        for role in roles
        for component in profile.component_sheets.get(role, [])
        if component.execution_state in states
    ]


def _has_incomplete_component(
    profile: K03ExecutionProfile,
    roles: tuple[str, ...],
) -> bool:
    return bool(_components_with_states(
        profile, roles, {COMPONENT_STATE_INCOMPLETE, COMPONENT_STATE_AMBIGUOUS}
    ))


def _first_component_dataset(
    profile: K03ExecutionProfile,
    datasets: list[K03SheetDataset],
    roles: tuple[str, ...],
) -> K03SheetDataset | None:
    for role in roles:
        for component in profile.component_sheets.get(role, []):
            dataset = _match_component_dataset(component, datasets)
            if dataset is not None:
                return dataset
    return None


def _match_component_dataset(
    component: K03ComponentSheet,
    datasets: list[K03SheetDataset],
) -> K03SheetDataset | None:
    return next(
        (
            dataset
            for dataset in datasets
            if dataset.sheet_name == component.sheet_name
            and dataset.execution_path == component.execution_path
            and dataset.template_type == component.template_type
        ),
        None,
    )


def _record_group_data_insufficient(
    recorder: RuleExecutionRecorder,
    rule_ids: tuple[str, ...],
    note: str,
) -> None:
    for rule_id in rule_ids:
        recorder.record_data_insufficient(rule_id, note)
        _attach_missing_observation(recorder, rule_id, note)


def _record_group_not_applicable(
    recorder: RuleExecutionRecorder,
    rule_ids: tuple[str, ...],
    dataset: K03SheetDataset | None,
    note: str,
) -> None:
    for rule_id in rule_ids:
        recorder.record_not_applicable(rule_id, note)
        if dataset is None:
            _attach_missing_observation(recorder, rule_id, note)
        else:
            _attach_path_not_applicable_observation(recorder, rule_id, dataset, note)


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
