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
