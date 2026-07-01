from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Iterable

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
_LEGACY_OBSERVATION_KEYS = {"path", "inputs", "checks", "notes"}
_EVIDENCE_OBSERVATION_KEYS = {
    "checked_data",
    "check_logic",
    "expected_result",
    "actual_result",
    "result_summary",
}
_OBSERVATION_PATHS = {
    "primary",
    "fallback",
    "alternative",
    "skipped",
    "data_insufficient",
    "not_applicable",
}
_INPUT_KEYS = {"source_sheet", "section", "field", "row", "column", "range"}
_CHECK_KEYS = {
    "name",
    "left_label",
    "left_value",
    "operator",
    "right_label",
    "right_value",
    "result",
}
_CHECK_OPERATORS = {
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "exists",
    "missing",
    "matched",
    "not_matched",
}
_CHECK_RESULTS = {"passed", "triggered", "not_applicable", "data_insufficient"}
_EVIDENCE_ITEM_KEYS = {
    "sheet",
    "section",
    "location",
    "identified_by",
    "key_columns",
    "values_read",
    "missing_data",
}
_IDENTIFIED_BY_KEYS = {
    "sheet_name",
    "section",
    "matched_keywords",
    "matched_rows",
    "matched_columns",
}
_VALUE_READ_KEYS = {
    "label",
    "value",
    "row",
    "column",
    "cell",
    "unit",
    "amount_type",
}
_MAX_INPUTS = 8
_MAX_CHECKS = 8
_MAX_NOTES = 5
_MAX_EVIDENCE_ITEMS = 8
_MAX_KEY_COLUMNS = 12
_MAX_VALUES_READ = 20
_MAX_MISSING_DATA = 12
_MAX_IDENTIFIED_TERMS = 12
_MAX_TEXT_LEN = 120
_MAX_HOW_TEXT_LEN = 500


@dataclass
class RuleExecutionRecord:
    rule_id: str
    status: str
    finding_count: int = 0
    status_note: str = ""
    observation: dict[str, Any] | None = None

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
        observation: dict[str, Any] | None = None,
        **kwargs: object,
    ) -> list[QcIssue]:
        issues = list(rule_fn(*args, **kwargs))
        finding_count = sum(1 for issue in issues if issue.severity != Severity.PASS)
        self.record_executed(rule_id, finding_count, observation=observation)
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
        observation: dict[str, Any] | None = None,
    ) -> None:
        checked_observation = validate_observation(observation)
        existing = self._records.get(rule_id)
        if existing is None:
            self._records[rule_id] = RuleExecutionRecord(
                rule_id=rule_id,
                status=STATUS_EXECUTED,
                finding_count=finding_count,
                status_note=note,
                observation=checked_observation,
            )
            return
        existing.status = STATUS_EXECUTED
        existing.finding_count += finding_count
        if note:
            existing.status_note = _merge_note(existing.status_note, note)
        if checked_observation is not None:
            existing.observation = checked_observation

    def record_observation(self, rule_id: str, observation: dict[str, Any]) -> None:
        existing = self._records.get(rule_id)
        if existing is None:
            raise ValueError(f"Cannot attach observation before recording rule: {rule_id}")
        existing.observation = validate_observation(observation)

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
        items = []
        for record in self._records.values():
            item = {
                "rule_id": record.rule_id,
                "status": record.status,
                "executed": record.executed,
                "finding_count": record.finding_count,
                "status_note": record.status_note,
            }
            if record.observation is not None:
                item["observation"] = record.observation
            items.append(item)
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





def validate_observation(observation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate bounded ledger observation; it is a fact summary, not a trace log."""
    if observation is None:
        return None
    if not isinstance(observation, dict):
        raise ValueError("execution observation must be a dict")
    keys = set(observation)
    if keys == _LEGACY_OBSERVATION_KEYS:
        return _validate_legacy_observation(observation)
    if keys == _EVIDENCE_OBSERVATION_KEYS:
        return _validate_evidence_observation(observation)
    raise ValueError(
        "execution observation must be either legacy path/inputs/checks/notes "
        "or evidence checked_data/check_logic/expected_result/actual_result/result_summary"
    )


def _validate_legacy_observation(observation: dict[str, Any]) -> dict[str, Any]:
    """Validate the original v1 observation shape for backward compatibility."""

    path = observation.get("path")
    if path is not None and path not in _OBSERVATION_PATHS:
        raise ValueError(f"unsupported execution observation path: {path}")

    inputs = observation.get("inputs")
    checks = observation.get("checks")
    notes = observation.get("notes")
    if not isinstance(inputs, list) or len(inputs) > _MAX_INPUTS:
        raise ValueError("execution observation inputs must be a bounded list")
    if not isinstance(checks, list) or len(checks) > _MAX_CHECKS:
        raise ValueError("execution observation checks must be a bounded list")
    if not isinstance(notes, list) or len(notes) > _MAX_NOTES:
        raise ValueError("execution observation notes must be a bounded list")

    checked_inputs = [_validate_input(item) for item in inputs]
    checked_checks = [_validate_check(item) for item in checks]
    checked_notes = [_validate_note(item) for item in notes]
    return {
        "path": path,
        "inputs": checked_inputs,
        "checks": checked_checks,
        "notes": checked_notes,
    }


def _validate_evidence_observation(observation: dict[str, Any]) -> dict[str, Any]:
    checked_data = observation.get("checked_data")
    if not isinstance(checked_data, list) or len(checked_data) > _MAX_EVIDENCE_ITEMS:
        raise ValueError("execution observation checked_data must be a bounded list")
    return {
        "checked_data": [_validate_evidence_item(item) for item in checked_data],
        "check_logic": _validate_how_text_or_none(
            observation.get("check_logic"), "check_logic"
        ),
        "expected_result": _validate_how_text_or_none(
            observation.get("expected_result"), "expected_result"
        ),
        "actual_result": _validate_how_text_or_none(
            observation.get("actual_result"), "actual_result"
        ),
        "result_summary": _validate_how_text_or_none(
            observation.get("result_summary"), "result_summary"
        ),
    }


def _validate_evidence_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != _EVIDENCE_ITEM_KEYS:
        raise ValueError("execution observation checked_data has unsupported fields")
    key_columns = item.get("key_columns")
    values_read = item.get("values_read")
    missing_data = item.get("missing_data")
    if not isinstance(key_columns, list) or len(key_columns) > _MAX_KEY_COLUMNS:
        raise ValueError("execution observation key_columns must be a bounded list")
    if not isinstance(values_read, list) or len(values_read) > _MAX_VALUES_READ:
        raise ValueError("execution observation values_read must be a bounded list")
    if not isinstance(missing_data, list) or len(missing_data) > _MAX_MISSING_DATA:
        raise ValueError("execution observation missing_data must be a bounded list")
    return {
        "sheet": _validate_short_text_or_none(item.get("sheet"), "checked_data.sheet"),
        "section": _validate_short_text_or_none(
            item.get("section"), "checked_data.section"
        ),
        "location": _validate_short_text_or_none(
            item.get("location"), "checked_data.location"
        ),
        "identified_by": _validate_identified_by(item.get("identified_by")),
        "key_columns": [
            _validate_short_text_or_none(value, "checked_data.key_columns")
            for value in key_columns
        ],
        "values_read": [_validate_value_read(value) for value in values_read],
        "missing_data": [
            _validate_short_text_or_none(value, "checked_data.missing_data")
            for value in missing_data
        ],
    }


def _validate_identified_by(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != _IDENTIFIED_BY_KEYS:
        raise ValueError("execution observation identified_by has unsupported fields")
    matched_keywords = item.get("matched_keywords")
    matched_rows = item.get("matched_rows")
    matched_columns = item.get("matched_columns")
    if not isinstance(matched_keywords, list) or len(matched_keywords) > _MAX_IDENTIFIED_TERMS:
        raise ValueError("execution observation matched_keywords must be a bounded list")
    if not isinstance(matched_rows, list) or len(matched_rows) > _MAX_IDENTIFIED_TERMS:
        raise ValueError("execution observation matched_rows must be a bounded list")
    if not isinstance(matched_columns, list) or len(matched_columns) > _MAX_IDENTIFIED_TERMS:
        raise ValueError("execution observation matched_columns must be a bounded list")
    return {
        "sheet_name": _validate_short_text_or_none(
            item.get("sheet_name"), "identified_by.sheet_name"
        ),
        "section": _validate_short_text_or_none(
            item.get("section"), "identified_by.section"
        ),
        "matched_keywords": [
            _validate_short_text_or_none(value, "identified_by.matched_keywords")
            for value in matched_keywords
        ],
        "matched_rows": [
            _validate_int_or_none(value, "identified_by.matched_rows")
            for value in matched_rows
        ],
        "matched_columns": [
            _validate_int_or_none(value, "identified_by.matched_columns")
            for value in matched_columns
        ],
    }


def _validate_value_read(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != _VALUE_READ_KEYS:
        raise ValueError("execution observation values_read has unsupported fields")
    return {
        "label": _validate_short_text_or_none(item.get("label"), "values_read.label"),
        "value": _validate_short_text_or_none(item.get("value"), "values_read.value"),
        "row": _validate_int_or_none(item.get("row"), "values_read.row"),
        "column": _validate_int_or_none(item.get("column"), "values_read.column"),
        "cell": _validate_short_text_or_none(item.get("cell"), "values_read.cell"),
        "unit": _validate_short_text_or_none(item.get("unit"), "values_read.unit"),
        "amount_type": _validate_short_text_or_none(
            item.get("amount_type"), "values_read.amount_type"
        ),
    }


def _validate_input(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != _INPUT_KEYS:
        raise ValueError("execution observation input has unsupported fields")
    checked: dict[str, Any] = {}
    for key in ("source_sheet", "section", "field", "range"):
        checked[key] = _validate_short_text_or_none(item.get(key), f"input.{key}")
    checked["row"] = _validate_int_or_none(item.get("row"), "input.row")
    checked["column"] = _validate_int_or_none(item.get("column"), "input.column")
    return checked


def _validate_check(item: Any) -> dict[str, str | None]:
    if not isinstance(item, dict) or set(item) != _CHECK_KEYS:
        raise ValueError("execution observation check has unsupported fields")
    operator = item.get("operator")
    result = item.get("result")
    if operator not in _CHECK_OPERATORS:
        raise ValueError(f"unsupported execution observation operator: {operator}")
    if result not in _CHECK_RESULTS:
        raise ValueError(f"unsupported execution observation result: {result}")
    return {
        "name": _validate_short_text_or_none(item.get("name"), "check.name"),
        "left_label": _validate_short_text_or_none(item.get("left_label"), "check.left_label"),
        "left_value": _validate_short_text_or_none(item.get("left_value"), "check.left_value"),
        "operator": operator,
        "right_label": _validate_short_text_or_none(item.get("right_label"), "check.right_label"),
        "right_value": _validate_short_text_or_none(item.get("right_value"), "check.right_value"),
        "result": result,
    }


def _validate_note(item: Any) -> str:
    if not isinstance(item, str):
        raise ValueError("execution observation note must be text")
    text = item.strip()
    if len(text) > _MAX_TEXT_LEN:
        raise ValueError("execution observation note is too long")
    return text


def _validate_short_text_or_none(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if len(text) > _MAX_TEXT_LEN:
        raise ValueError(f"execution observation {field} is too long")
    return text


def _validate_how_text_or_none(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if len(text) > _MAX_HOW_TEXT_LEN:
        raise ValueError(f"execution observation {field} is too long")
    return text


def _validate_int_or_none(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"execution observation {field} must be an integer or null")
    return value

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
