from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Iterable

from rules.models import QcIssue, Severity

STATUS_EXECUTED = "EXECUTED"
STATUS_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
_ALLOWED_STATUSES = {STATUS_EXECUTED, STATUS_DATA_INSUFFICIENT, STATUS_NOT_APPLICABLE}
_STATUS_PRIORITY = {
    STATUS_NOT_APPLICABLE: 1,
    STATUS_DATA_INSUFFICIENT: 2,
    STATUS_EXECUTED: 3,
}


@dataclass
class RuleExecutionRecord:
    rule_id: str
    status: str
    finding_count: int = 0
    status_note: str = ""

    @property
    def executed(self) -> bool:
        return self.status == STATUS_EXECUTED


class RuleExecutionRecorder:
    """Observed rule execution recorder.

    v1.1-lite is facts-only: it records rule execution and explicit runner
    non-execution branches. It does not infer coverage, expected rules, or SOP gaps.
    """

    def __init__(self) -> None:
        self._records: OrderedDict[str, RuleExecutionRecord] = OrderedDict()

    def execute_rule(
        self,
        rule_id: str,
        rule_fn: Callable[..., Iterable[QcIssue]],
        *args: object,
        **kwargs: object,
    ) -> list[QcIssue]:
        issues = list(rule_fn(*args, **kwargs))
        finding_count = sum(1 for issue in issues if issue.severity != Severity.PASS)
        self.record_executed(rule_id, finding_count)
        return issues

    def record(self, rule_id: str, finding_count: int) -> None:
        """Backward-compatible alias for observed executed rules."""
        self.record_executed(rule_id, finding_count)

    def record_executed(
        self,
        rule_id: str,
        finding_count: int = 0,
        *,
        note: str = "",
    ) -> None:
        existing = self._records.get(rule_id)
        if existing is None:
            self._records[rule_id] = RuleExecutionRecord(
                rule_id=rule_id,
                status=STATUS_EXECUTED,
                finding_count=finding_count,
                status_note=note,
            )
            return
        existing.status = STATUS_EXECUTED
        existing.finding_count += finding_count
        if note:
            existing.status_note = _merge_note(existing.status_note, note)

    def record_data_insufficient(self, rule_id: str, note: str) -> None:
        self._record_non_execution(rule_id, STATUS_DATA_INSUFFICIENT, note)

    def record_not_applicable(self, rule_id: str, note: str) -> None:
        self._record_non_execution(rule_id, STATUS_NOT_APPLICABLE, note)

    def _record_non_execution(self, rule_id: str, status: str, note: str) -> None:
        if status not in _ALLOWED_STATUSES or status == STATUS_EXECUTED:
            raise ValueError(f"Unsupported non-execution status: {status}")
        existing = self._records.get(rule_id)
        if existing is None:
            self._records[rule_id] = RuleExecutionRecord(
                rule_id=rule_id,
                status=status,
                finding_count=0,
                status_note=note,
            )
            return
        if existing.status == STATUS_EXECUTED:
            return
        if _STATUS_PRIORITY[status] > _STATUS_PRIORITY[existing.status]:
            existing.status = status
        existing.status_note = _merge_note(existing.status_note, note)

    def executed_rule_ids(self) -> list[str]:
        """Return observed checkpoint ids, kept for report.rule_ids compatibility."""
        return list(self._records.keys())

    def to_ledger(self) -> dict:
        items = [
            {
                "rule_id": record.rule_id,
                "status": record.status,
                "executed": record.executed,
                "finding_count": record.finding_count,
                "status_note": record.status_note,
            }
            for record in self._records.values()
        ]
        executed = sum(1 for item in items if item["status"] == STATUS_EXECUTED)
        data_insufficient = sum(
            1 for item in items if item["status"] == STATUS_DATA_INSUFFICIENT
        )
        not_applicable = sum(
            1 for item in items if item["status"] == STATUS_NOT_APPLICABLE
        )
        rules_with_findings = sum(
            1
            for item in items
            if item["status"] == STATUS_EXECUTED and item["finding_count"] > 0
        )
        return {
            "summary": {
                "total_observed_checkpoints": len(items),
                "executed": executed,
                "data_insufficient": data_insufficient,
                "not_applicable": not_applicable,
                # Backward-compatible v1 fields for the current UI/report consumers.
                "executed_rules": executed,
                "rules_with_findings": rules_with_findings,
                "rules_without_findings": executed - rules_with_findings,
            },
            "items": items,
        }


def _merge_note(existing: str, note: str) -> str:
    note = str(note or "").strip()
    if not note:
        return existing
    existing = str(existing or "").strip()
    if not existing:
        return note
    if note in existing.split("；"):
        return existing
    return f"{existing}；{note}"


def validate_execution_ledger(ledger: dict, issues: Iterable[QcIssue]) -> None:
    items = ledger.get("items", [])
    item_by_rule = {item.get("rule_id"): item for item in items}
    missing = sorted({issue.rule_id for issue in issues} - set(item_by_rule))
    if missing:
        raise ValueError(
            "execution_ledger missing observed issue rule_id(s): " + ", ".join(missing)
        )
    non_executed_issue_rules = sorted(
        {
            issue.rule_id
            for issue in issues
            if item_by_rule.get(issue.rule_id, {}).get("status") != STATUS_EXECUTED
        }
    )
    if non_executed_issue_rules:
        raise ValueError(
            "execution_ledger has issue rule_id(s) not marked EXECUTED: "
            + ", ".join(non_executed_issue_rules)
        )

    summary = ledger.get("summary", {})
    executed = sum(1 for item in items if item.get("status") == STATUS_EXECUTED)
    data_insufficient = sum(
        1 for item in items if item.get("status") == STATUS_DATA_INSUFFICIENT
    )
    not_applicable = sum(
        1 for item in items if item.get("status") == STATUS_NOT_APPLICABLE
    )
    if summary.get("total_observed_checkpoints") != len(items):
        raise ValueError("execution_ledger summary total_observed_checkpoints is inconsistent")
    if summary.get("executed") != executed:
        raise ValueError("execution_ledger summary executed is inconsistent")
    if summary.get("data_insufficient") != data_insufficient:
        raise ValueError("execution_ledger summary data_insufficient is inconsistent")
    if summary.get("not_applicable") != not_applicable:
        raise ValueError("execution_ledger summary not_applicable is inconsistent")
    if executed + data_insufficient + not_applicable != len(items):
        raise ValueError("execution_ledger status buckets are inconsistent")
