from __future__ import annotations

import rules.k03_runner as k03_runner
from ingest.k03_sheet import (
    COMPONENT_STATE_EXECUTED,
    EXECUTION_PATH_POLICY_REVIEW,
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING,
    EXECUTION_PATH_TOD_BY_ITEM,
    EXECUTION_PATH_TOD_SAMPLING,
    EXECUTION_PATH_UNKNOWN,
    K03_BRANCH_DEPRECIATION_TEST,
    K03_BRANCH_POLICY_REVIEW,
    K03ComponentSheet,
    K03ExecutionProfile,
    K03SheetDataset,
)
from rules.execution_recorder import (
    STATUS_DATA_INSUFFICIENT,
    STATUS_NOT_APPLICABLE,
    RuleExecutionRecorder,
)


def _dataset(
    sheet_name: str,
    execution_path: str,
    *,
    template_type: str,
    branch: str = K03_BRANCH_DEPRECIATION_TEST,
) -> K03SheetDataset:
    return K03SheetDataset(
        workbook_name="test.xlsx",
        source_file="test.xlsx",
        sheet_name=sheet_name,
        k03_branch=branch,
        execution_path=execution_path,
        template_type=template_type,
    )


def _component(role: str, dataset: K03SheetDataset) -> K03ComponentSheet:
    return K03ComponentSheet(
        role=role,
        sheet_name=dataset.sheet_name,
        execution_path=dataset.execution_path,
        template_type=dataset.template_type,
        execution_state=COMPONENT_STATE_EXECUTED,
    )


def _install_spies(monkeypatch):
    calls: list[tuple] = []

    def fake_sap(dataset, **kwargs):
        calls.append(("sap", dataset.sheet_name, kwargs.get("k03_execution_profile")))
        return []

    def fake_by_item(dataset, **kwargs):
        calls.append(("by_item", dataset.sheet_name))
        return []

    def fake_sampling(dataset, *, sample_output=None, **kwargs):
        calls.append(
            (
                "sampling",
                dataset.sheet_name if dataset else None,
                sample_output.sheet_name if sample_output else None,
            )
        )
        return []

    def fake_policy(dataset, **kwargs):
        calls.append(("policy", dataset.sheet_name))
        return []

    monkeypatch.setattr(k03_runner, "run_k03_sap_rules", fake_sap)
    monkeypatch.setattr(k03_runner, "run_k03_tod_by_item_rules", fake_by_item)
    monkeypatch.setattr(k03_runner, "run_k03_tod_sampling_rules", fake_sampling)
    monkeypatch.setattr(k03_runner, "run_k03_policy_review_rules", fake_policy)
    return calls


def _ledger_items(recorder: RuleExecutionRecorder) -> dict[str, dict]:
    return {item["rule_id"]: item for item in recorder.to_ledger()["items"]}


def test_profile_routes_tod_by_item_only_and_keeps_policy_independent(monkeypatch):
    by_item = _dataset(
        "K.03.2 TOD by item",
        EXECUTION_PATH_TOD_BY_ITEM,
        template_type="tod_by_item",
    )
    policy = _dataset(
        "K.03.3 Policy",
        EXECUTION_PATH_POLICY_REVIEW,
        template_type="policy_review",
        branch=K03_BRANCH_POLICY_REVIEW,
    )
    profile = K03ExecutionProfile(
        primary_depreciation_path=EXECUTION_PATH_TOD_BY_ITEM,
        component_sheets={
            "tod_by_item": [_component("tod_by_item", by_item)],
            "policy_review": [_component("policy_review", policy)],
        },
    )
    recorder = RuleExecutionRecorder()
    calls = _install_spies(monkeypatch)

    k03_runner.run_k03_rules(
        [by_item, policy],
        k03_execution_profile=profile,
        recorder=recorder,
    )

    assert calls == [("by_item", by_item.sheet_name), ("policy", policy.sheet_name)]
    ledger = _ledger_items(recorder)
    assert all(ledger[rule_id]["status"] == STATUS_NOT_APPLICABLE for rule_id in k03_runner.K03_SAP_RULE_IDS)
    assert all(ledger[rule_id]["status"] == STATUS_NOT_APPLICABLE for rule_id in k03_runner.K03_TOD_SAMPLING_RULE_IDS)


def test_profile_routes_sap_plus_tod_sampling_combination(monkeypatch):
    sap = _dataset(
        "K.03.1 SAP medium",
        EXECUTION_PATH_SAP_MEDIUM,
        template_type="sap_medium_precision",
    )
    sampling = _dataset(
        "K.03.2 TOD sampling",
        EXECUTION_PATH_TOD_SAMPLING,
        template_type="tod_sampling",
    )
    output = _dataset(
        "K.03.2a Sample output",
        EXECUTION_PATH_TOD_SAMPLING,
        template_type="tod_sampling_output",
    )
    policy = _dataset(
        "K.03.3 Policy",
        EXECUTION_PATH_POLICY_REVIEW,
        template_type="policy_review",
        branch=K03_BRANCH_POLICY_REVIEW,
    )
    profile = K03ExecutionProfile(
        primary_depreciation_path=EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING,
        component_sheets={
            "sap_medium": [_component("sap_medium", sap)],
            "tod_sampling": [_component("tod_sampling", sampling)],
            "tod_sampling_output": [_component("tod_sampling_output", output)],
            "policy_review": [_component("policy_review", policy)],
        },
    )
    recorder = RuleExecutionRecorder()
    calls = _install_spies(monkeypatch)

    k03_runner.run_k03_rules(
        [sap, sampling, output, policy],
        k03_execution_profile=profile,
        recorder=recorder,
    )

    assert calls == [
        ("sap", sap.sheet_name, profile),
        ("sampling", sampling.sheet_name, output.sheet_name),
        ("policy", policy.sheet_name),
    ]
    ledger = _ledger_items(recorder)
    assert all(ledger[rule_id]["status"] == STATUS_NOT_APPLICABLE for rule_id in k03_runner.K03_TOD_BY_ITEM_RULE_IDS)


def test_profile_executes_every_actually_executed_depreciation_path(monkeypatch):
    medium = _dataset("SAP medium", EXECUTION_PATH_SAP_MEDIUM, template_type="sap_medium_precision")
    high = _dataset("SAP high", EXECUTION_PATH_SAP_HIGH, template_type="sap_high_precision")
    by_item = _dataset("TOD by item", EXECUTION_PATH_TOD_BY_ITEM, template_type="tod_by_item")
    sampling = _dataset("TOD sampling", EXECUTION_PATH_TOD_SAMPLING, template_type="tod_sampling")
    profile = K03ExecutionProfile(
        executed_depreciation_paths=[
            EXECUTION_PATH_SAP_MEDIUM, EXECUTION_PATH_SAP_HIGH,
            EXECUTION_PATH_TOD_BY_ITEM, EXECUTION_PATH_TOD_SAMPLING,
        ],
        component_sheets={
            "sap_medium": [_component("sap_medium", medium)],
            "sap_high": [_component("sap_high", high)],
            "tod_by_item": [_component("tod_by_item", by_item)],
            "tod_sampling": [_component("tod_sampling", sampling)],
        },
    )
    calls = _install_spies(monkeypatch)

    k03_runner.run_k03_rules(
        [medium, high, by_item, sampling],
        k03_execution_profile=profile,
        recorder=RuleExecutionRecorder(),
    )

    assert [call[0] for call in calls] == ["sap", "sap", "by_item", "sampling"]


def test_multiple_sap_paths_keep_observations_for_every_checked_sheet(monkeypatch):
    medium = _dataset("SAP medium", EXECUTION_PATH_SAP_MEDIUM, template_type="sap_medium_precision")
    high = _dataset("SAP high", EXECUTION_PATH_SAP_HIGH, template_type="sap_high_precision")
    profile = K03ExecutionProfile(
        executed_depreciation_paths=[EXECUTION_PATH_SAP_MEDIUM, EXECUTION_PATH_SAP_HIGH],
        component_sheets={
            "sap_medium": [_component("sap_medium", medium)],
            "sap_high": [_component("sap_high", high)],
        },
    )
    recorder = RuleExecutionRecorder()

    def fake_sap(dataset, *, recorder, **kwargs):
        recorder.record_executed(
            "sap_te_consistency",
            0,
            observation={
                "checked_data": [{
                    "sheet": dataset.sheet_name,
                    "section": "K.03.1 SAP 折旧测试",
                    "location": None,
                    "identified_by": {
                        "sheet_name": dataset.sheet_name,
                        "section": "K.03.1 SAP 折旧测试",
                        "matched_keywords": [dataset.sheet_name],
                        "matched_rows": [],
                        "matched_columns": [],
                    },
                    "key_columns": ["sap_te"],
                    "values_read": [],
                    "missing_data": [],
                }],
                "check_logic": "检查 SAP TE。",
                "expected_result": "SAP TE 与 Lead 一致。",
                "actual_result": f"已检查 {dataset.sheet_name}。",
                "result_summary": "未触发 finding。",
            },
        )
        return []

    monkeypatch.setattr(k03_runner, "run_k03_sap_rules", fake_sap)
    monkeypatch.setattr(k03_runner, "run_k03_tod_by_item_rules", lambda *args, **kwargs: [])
    monkeypatch.setattr(k03_runner, "run_k03_tod_sampling_rules", lambda *args, **kwargs: [])
    monkeypatch.setattr(k03_runner, "run_k03_policy_review_rules", lambda *args, **kwargs: [])

    k03_runner.run_k03_rules(
        [medium, high],
        k03_execution_profile=profile,
        recorder=recorder,
    )

    observation = _ledger_items(recorder)["sap_te_consistency"]["observation"]
    assert [item["sheet"] for item in observation["checked_data"]] == [
        "SAP medium",
        "SAP high",
    ]


def test_profile_reports_missing_policy_independently(monkeypatch):
    sap = _dataset(
        "K.03.1 SAP high",
        EXECUTION_PATH_SAP_HIGH,
        template_type="sap_high_precision",
    )
    profile = K03ExecutionProfile(
        primary_depreciation_path=EXECUTION_PATH_SAP_HIGH,
        component_sheets={"sap_high": [_component("sap_high", sap)]},
    )
    recorder = RuleExecutionRecorder()
    calls = _install_spies(monkeypatch)

    k03_runner.run_k03_rules(
        [sap],
        k03_execution_profile=profile,
        recorder=recorder,
    )

    assert calls == [("sap", sap.sheet_name, profile)]
    ledger = _ledger_items(recorder)
    assert all(ledger[rule_id]["status"] == STATUS_DATA_INSUFFICIENT for rule_id in k03_runner.K03_POLICY_REVIEW_RULE_IDS)


def test_profile_does_not_treat_current_depreciation_as_a_procedure(monkeypatch):
    profile = K03ExecutionProfile(
        primary_depreciation_path=EXECUTION_PATH_UNKNOWN,
        component_sheets={
            "auxiliary_current_depreciation": [
                K03ComponentSheet(
                    role="auxiliary_current_depreciation",
                    sheet_name="Current depreciation",
                    execution_path=EXECUTION_PATH_UNKNOWN,
                    template_type="auxiliary_current_depreciation",
                    evidence={"is_required_procedure_page": False},
                )
            ]
        },
    )
    recorder = RuleExecutionRecorder()
    calls = _install_spies(monkeypatch)

    k03_runner.run_k03_rules(
        [],
        k03_execution_profile=profile,
        recorder=recorder,
    )

    assert calls == []
    ledger = _ledger_items(recorder)
    assert set(ledger) == set(k03_runner.K03_RULE_IDS)
    assert all(item["status"] == STATUS_DATA_INSUFFICIENT for item in ledger.values())
