from __future__ import annotations

import pytest

from ingest.k03_sheet import (
    COMPONENT_STATE_AMBIGUOUS,
    COMPONENT_STATE_EXECUTED,
    COMPONENT_STATE_INCOMPLETE,
    COMPONENT_STATE_TEMPLATE_ONLY,
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_TOD_BY_ITEM,
    EXECUTION_PATH_TOD_SAMPLING,
    EXECUTION_PATH_UNKNOWN,
    K03ComponentSheet,
    K03ExecutionProfile,
)
from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.execution_recorder import (
    STATUS_DATA_INSUFFICIENT,
    STATUS_EXECUTED,
    STATUS_NOT_APPLICABLE,
    RuleExecutionRecorder,
)
from rules.k03_execution_control import RULE_IDS, run_k03_execution_control


def _summary(sap="否", tod="否", policy="否", *, extra=None):
    values = [("K.03.1 SAP", "K.03.1", sap), ("K.03.2 TOD", "K.03.2", tod), ("K.03.3 折旧政策", "K.03.3", policy)]
    values.extend(extra or [])
    return SummarySheetDataset(
        source_file="test.xlsx",
        source_sheet="汇总",
        header_row=1,
        programs=[PspProgramRow(name, ref, status, None, None, row) for row, (name, ref, status) in enumerate(values, 10)],
    )


def _component(role, state=COMPONENT_STATE_EXECUTED, *, index=1):
    paths = {
        "sap_medium": EXECUTION_PATH_SAP_MEDIUM,
        "sap_high": EXECUTION_PATH_SAP_HIGH,
        "tod_by_item": EXECUTION_PATH_TOD_BY_ITEM,
        "tod_sampling": EXECUTION_PATH_TOD_SAMPLING,
        "tod_sampling_output": EXECUTION_PATH_TOD_SAMPLING,
        "policy_review": "policy_review",
        "unknown_depreciation_test": EXECUTION_PATH_UNKNOWN,
    }
    return K03ComponentSheet(role, f"{role}-{index}", paths[role], role, state)


def _profile(*components, primary=EXECUTION_PATH_UNKNOWN):
    grouped = {}
    for item in components:
        grouped.setdefault(item.role, []).append(item)
    return K03ExecutionProfile(primary_depreciation_path=primary, component_sheets=grouped)


def _run(summary, profile):
    recorder = RuleExecutionRecorder()
    issues = run_k03_execution_control(summary, profile, recorder=recorder)
    ledger = {item["rule_id"]: item for item in recorder.to_ledger()["items"]}
    return issues, ledger


@pytest.mark.parametrize(
    ("summary", "profile"),
    [
        (_summary(sap="是"), _profile(_component("sap_medium"))),
        (_summary(tod="是"), _profile(_component("tod_by_item"))),
        (_summary(sap="是", tod="是"), _profile(_component("sap_medium"), _component("tod_sampling"))),
        (_summary(sap="是", tod="是"), _profile(_component("sap_high"), _component("tod_by_item"))),
    ],
)
def test_normal_single_or_sap_plus_tod_paths_do_not_raise_findings(summary, profile):
    issues, ledger = _run(summary, profile)
    assert issues == []
    assert ledger[RULE_IDS[0]]["status"] == STATUS_EXECUTED
    assert ledger[RULE_IDS[1]]["status"] == STATUS_EXECUTED
    assert ledger[RULE_IDS[2]]["status"] == STATUS_EXECUTED


@pytest.mark.parametrize(
    "components",
    [
        (_component("sap_medium"), _component("sap_high")),
        (_component("tod_by_item"), _component("tod_sampling")),
        (_component("sap_medium", index=1), _component("sap_medium", index=2)),
    ],
)
def test_conflicting_executed_path_combinations_need_review(components):
    issues, ledger = _run(_summary(sap="是", tod="是"), _profile(*components))
    assert any(issue.rule_id == RULE_IDS[2] for issue in issues)
    assert ledger[RULE_IDS[2]]["status"] == STATUS_EXECUTED
    assert ledger[RULE_IDS[2]]["finding_count"] == 1


@pytest.mark.parametrize(
    "profile",
    [
        _profile(_component("tod_sampling_output")),
        _profile(_component("sap_medium"), _component("sap_high", COMPONENT_STATE_INCOMPLETE)),
        _profile(_component("unknown_depreciation_test", COMPONENT_STATE_AMBIGUOUS)),
    ],
)
def test_unresolved_or_output_only_paths_are_data_insufficient(profile):
    _, ledger = _run(_summary(sap="是"), profile)
    assert ledger[RULE_IDS[2]]["status"] == STATUS_DATA_INSUFFICIENT


def test_summary_yes_without_executed_component_is_consistency_finding_but_path_data_insufficient():
    issues, ledger = _run(_summary(sap="是"), _profile(_component("sap_medium", COMPONENT_STATE_TEMPLATE_ONLY)))
    assert [issue.rule_id for issue in issues] == [RULE_IDS[0]]
    assert ledger[RULE_IDS[0]]["status"] == STATUS_EXECUTED
    assert ledger[RULE_IDS[1]]["status"] == STATUS_DATA_INSUFFICIENT


def test_summary_no_with_executed_component_is_consistency_finding():
    issues, ledger = _run(_summary(tod="否"), _profile(_component("tod_sampling")))
    assert any(issue.field == "tod_execution_status" for issue in issues)
    assert ledger[RULE_IDS[0]]["status"] == STATUS_EXECUTED


def test_missing_summary_row_with_executed_component_is_consistency_finding():
    summary = _summary()
    summary.programs = [row for row in summary.programs if "K.03.3" not in (row.sheet_ref or "")]
    issues, _ = _run(summary, _profile(_component("policy_review")))
    assert any(issue.field == "policy_execution_status" for issue in issues)


def test_policy_is_compared_independently_from_sap_and_tod():
    issues, _ = _run(_summary(sap="是", policy="是"), _profile(_component("sap_medium")))
    assert any(issue.field == "policy_execution_status" for issue in issues)


def test_conflicting_duplicate_summary_statuses_need_review():
    summary = _summary(sap="是", extra=[("K.03.1 SAP duplicate", "K.03.1", "否")])
    issues, ledger = _run(summary, _profile(_component("sap_medium")))
    assert any(issue.field == "sap_execution_status" for issue in issues)
    assert ledger[RULE_IDS[0]]["status"] == STATUS_EXECUTED


def test_k032a_auxiliary_row_is_not_treated_as_tod_program():
    summary = _summary(tod="是", extra=[("选样输出", "K.03.2a", None)])
    issues, _ = _run(summary, _profile(_component("tod_sampling")))
    assert issues == []


def test_primary_path_is_not_used_as_execution_evidence():
    issues, ledger = _run(_summary(sap="是"), _profile(primary=EXECUTION_PATH_SAP_HIGH))
    assert any(issue.field == "sap_execution_status" for issue in issues)
    assert ledger[RULE_IDS[1]]["status"] == STATUS_DATA_INSUFFICIENT


def test_summary_both_depreciation_programs_no_makes_path_rule_not_applicable():
    _, ledger = _run(_summary(), _profile())
    assert ledger[RULE_IDS[1]]["status"] == STATUS_NOT_APPLICABLE
    assert ledger[RULE_IDS[2]]["status"] == STATUS_NOT_APPLICABLE


@pytest.mark.parametrize("state", [COMPONENT_STATE_INCOMPLETE, COMPONENT_STATE_AMBIGUOUS])
def test_summary_no_with_uncertain_policy_is_not_claimed_as_comparable(state):
    issues, ledger = _run(_summary(), _profile(_component("policy_review", state)))
    assert not any(issue.field == "policy_execution_status" for issue in issues)
    assert ledger[RULE_IDS[0]]["status"] == STATUS_DATA_INSUFFICIENT


def test_orphan_executed_sampling_output_makes_program_consistency_data_insufficient():
    issues, ledger = _run(_summary(), _profile(_component("tod_sampling_output")))
    assert issues == []
    assert ledger[RULE_IDS[0]]["status"] == STATUS_DATA_INSUFFICIENT


def test_definite_status_is_compared_when_duplicate_row_is_blank():
    summary = _summary(sap="是", extra=[("K.03.1 SAP detail", "K.03.1", None)])
    issues, ledger = _run(summary, _profile())
    assert any(issue.field == "sap_execution_status" for issue in issues)
    assert ledger[RULE_IDS[0]]["status"] == STATUS_EXECUTED


def test_unrelated_non_k03_sap_row_is_not_classified_by_semantic_fallback():
    summary = _summary()
    summary.programs.append(PspProgramRow("SAP data migration", "IT.01", "是", None, None, 20))
    issues, _ = _run(summary, _profile())
    assert issues == []


def test_observation_records_component_sheet_name():
    _, ledger = _run(_summary(sap="是"), _profile(_component("sap_medium")))
    values = ledger[RULE_IDS[2]]["observation"]["checked_data"][1]["values_read"]
    assert values[0]["label"] == "sap_medium / sap_medium-1"
