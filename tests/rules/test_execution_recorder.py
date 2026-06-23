from __future__ import annotations

import pytest

from rules.execution_recorder import RuleExecutionRecorder, validate_execution_ledger
from rules.models import QcIssue, Severity


def _issue(rule_id: str, severity: Severity = Severity.FAIL) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=rule_id,
        field=None,
        severity=severity,
        message="test issue",
        suggestion="fix it",
    )


def test_execution_ledger_v11_summary_counts_three_statuses():
    recorder = RuleExecutionRecorder()
    recorder.record_executed("executed_without_finding", 0)
    recorder.record_executed("executed_with_finding", 2)
    recorder.record_data_insufficient("missing_data_rule", "缺少资料")
    recorder.record_not_applicable("not_applicable_rule", "当前场景不适用")

    ledger = recorder.to_ledger()

    assert ledger["summary"]["total_observed_checkpoints"] == 4
    assert ledger["summary"]["executed"] == 2
    assert ledger["summary"]["data_insufficient"] == 1
    assert ledger["summary"]["not_applicable"] == 1
    assert ledger["summary"]["executed_rules"] == 2
    assert ledger["summary"]["rules_with_findings"] == 1
    assert ledger["summary"]["rules_without_findings"] == 1
    assert {item["status"] for item in ledger["items"]} == {
        "EXECUTED",
        "DATA_INSUFFICIENT",
        "NOT_APPLICABLE",
    }


def test_execution_ledger_executed_overrides_prior_non_execution():
    recorder = RuleExecutionRecorder()
    recorder.record_data_insufficient("late_rule", "先缺资料")
    recorder.record_executed("late_rule", 1)

    item = recorder.to_ledger()["items"][0]

    assert item["rule_id"] == "late_rule"
    assert item["status"] == "EXECUTED"
    assert item["executed"] is True
    assert item["finding_count"] == 1


def test_validate_execution_ledger_requires_issue_rule_to_be_executed():
    recorder = RuleExecutionRecorder()
    recorder.record_data_insufficient("rule_with_issue", "缺少资料")
    ledger = recorder.to_ledger()

    with pytest.raises(ValueError, match="not marked EXECUTED"):
        validate_execution_ledger(ledger, [_issue("rule_with_issue")])


def test_validate_execution_ledger_accepts_executed_issue_rule():
    recorder = RuleExecutionRecorder()
    recorder.record_executed("rule_with_issue", 1)
    ledger = recorder.to_ledger()

    validate_execution_ledger(ledger, [_issue("rule_with_issue")])



def _observation() -> dict:
    return {
        "path": "primary",
        "inputs": [
            {
                "source_sheet": "K.01 Agree SL to GL",
                "section": "b4_table3_check_with_table1",
                "field": "table3_check_values",
                "row": 42,
                "column": None,
                "range": None,
            }
        ],
        "checks": [
            {
                "name": "difference_vs_sad",
                "left_label": "max_difference",
                "left_value": "120000",
                "operator": ">",
                "right_label": "SAD",
                "right_value": "50000",
                "result": "triggered",
            }
        ],
        "notes": ["Used primary table3 check values"],
    }


def test_execution_ledger_records_bounded_observation_without_changing_summary():
    recorder = RuleExecutionRecorder()
    recorder.record_executed("observed_rule", 1, observation=_observation())

    ledger = recorder.to_ledger()
    item = ledger["items"][0]

    assert ledger["summary"]["total_observed_checkpoints"] == 1
    assert ledger["summary"]["executed"] == 1
    assert item["observation"]["path"] == "primary"
    assert set(item["observation"]) == {"path", "inputs", "checks", "notes"}
    assert set(item["observation"]["inputs"][0]) == {
        "source_sheet",
        "section",
        "field",
        "row",
        "column",
        "range",
    }
    assert set(item["observation"]["checks"][0]) == {
        "name",
        "left_label",
        "left_value",
        "operator",
        "right_label",
        "right_value",
        "result",
    }


def test_execution_observation_rejects_arbitrary_top_level_keys():
    recorder = RuleExecutionRecorder()
    obs = _observation()
    obs["free_form_log"] = []

    with pytest.raises(ValueError, match="only path, inputs, checks, notes"):
        recorder.record_executed("bad_observation", 0, observation=obs)


def test_execution_observation_rejects_unbounded_inputs():
    recorder = RuleExecutionRecorder()
    obs = _observation()
    obs["inputs"] = obs["inputs"] * 9

    with pytest.raises(ValueError, match="inputs must be a bounded list"):
        recorder.record_executed("bad_observation", 0, observation=obs)


def test_execution_observation_rejects_nested_arbitrary_input_fields():
    recorder = RuleExecutionRecorder()
    obs = _observation()
    obs["inputs"][0]["raw_row"] = {"full": "workpaper row"}

    with pytest.raises(ValueError, match="input has unsupported fields"):
        recorder.record_executed("bad_observation", 0, observation=obs)


def test_execution_observation_rejects_free_form_long_notes():
    recorder = RuleExecutionRecorder()
    obs = _observation()
    obs["notes"] = ["x" * 121]

    with pytest.raises(ValueError, match="note is too long"):
        recorder.record_executed("bad_observation", 0, observation=obs)
