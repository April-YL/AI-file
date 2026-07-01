from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rules.addition_runner import ADDITION_RULE_IDS
from rules.disposal_runner import DISPOSAL_RULE_IDS
from rules.k03_runner import K03_RULE_IDS
from rules.lead_runner import LEAD_RULE_IDS
from rules.registry import RuleSpec, get_by_rule_id, iter_implemented
from rules.rollforward_runner import ROLLFORWARD_RULE_IDS
from rules.runner import FA_LIST_RULE_IDS

OBSERVATION_EVIDENCE_LEVEL = "EVIDENCE_LEVEL"
OBSERVATION_LEGACY = "LEGACY"
OBSERVATION_MISSING = "MISSING"

NEXT_ACTION_DONE = "DONE"
NEXT_ACTION_NEED_HOW = "NEED_HOW"
NEXT_ACTION_NOT_EXECUTED = "NOT_EXECUTED"
NEXT_ACTION_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"

STATUS_EXECUTED = "EXECUTED"
STATUS_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"

_EVIDENCE_OBSERVATION_KEYS = {
    "checked_data",
    "check_logic",
    "expected_result",
    "actual_result",
    "result_summary",
}
_LEGACY_OBSERVATION_KEYS = {"path", "inputs", "checks", "notes"}

_PIPELINE_RULE_IDS = (
    "psp_completion",
    "addition_test_package_complete",
    "disposal_test_package_complete",
    "first_delivery_standard",
    "final_delivery_standard",
)
_RUNNER_ONLY_LEDGER_RULE_IDS = ("lead_ingest_readability",)


def default_runner_ledger_rule_ids() -> tuple[str, ...]:
    """Return the explicit rule ids that current runners can record in ledger."""

    return _dedupe(
        (
            *FA_LIST_RULE_IDS,
            *_PIPELINE_RULE_IDS,
            *DISPOSAL_RULE_IDS,
            *ADDITION_RULE_IDS,
            *K03_RULE_IDS,
            *LEAD_RULE_IDS,
            *_RUNNER_ONLY_LEDGER_RULE_IDS,
            *ROLLFORWARD_RULE_IDS,
        )
    )


def build_how_coverage_diagnostics(
    execution_ledger: dict[str, Any] | None,
    *,
    runner_rule_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a read-only HOW coverage report from registry, runner ids, and ledger.

    The function classifies existing observation facts only. It does not infer
    which rules should have executed for a workbook and does not mutate ledger.
    """

    runner_ids = _dedupe(runner_rule_ids or default_runner_ledger_rule_ids())
    implemented_specs = list(iter_implemented())
    implemented_ids = _dedupe(spec.rule_id for spec in implemented_specs)
    ledger_items = _ledger_items(execution_ledger)
    item_by_rule_id = {
        str(item.get("rule_id")): item
        for item in ledger_items
        if item.get("rule_id") is not None
    }

    row_rule_ids = _dedupe((*runner_ids, *implemented_ids, *item_by_rule_id.keys()))
    rows = [
        _build_row(rule_id, item_by_rule_id.get(rule_id))
        for rule_id in row_rule_ids
    ]

    ledger_observation_types = [
        classify_observation_type(item.get("observation"))
        for item in item_by_rule_id.values()
    ]
    has_observation_count = sum(
        1 for item in item_by_rule_id.values() if isinstance(item.get("observation"), dict)
    )
    evidence_count = sum(
        1
        for observation_type in ledger_observation_types
        if observation_type == OBSERVATION_EVIDENCE_LEVEL
    )
    legacy_count = sum(
        1
        for observation_type in ledger_observation_types
        if observation_type == OBSERVATION_LEGACY
    )
    missing_count = sum(
        1
        for observation_type in ledger_observation_types
        if observation_type == OBSERVATION_MISSING
    )

    return {
        "summary": {
            "registry_implemented_rule_count": len(implemented_ids),
            "runner_ledger_rule_count": len(runner_ids),
            "ledger_recorded_rule_count": len(item_by_rule_id),
            "rules_with_observation_count": has_observation_count,
            "evidence_level_how_count": evidence_count,
            "legacy_observation_count": legacy_count,
            "missing_observation_count": missing_count,
        },
        "rules": rows,
    }


def classify_observation_type(observation: Any) -> str:
    if not isinstance(observation, dict):
        return OBSERVATION_MISSING
    keys = set(observation)
    if _EVIDENCE_OBSERVATION_KEYS.issubset(keys):
        return OBSERVATION_EVIDENCE_LEVEL
    if _LEGACY_OBSERVATION_KEYS.issubset(keys):
        return OBSERVATION_LEGACY
    return OBSERVATION_LEGACY


def _build_row(rule_id: str, ledger_item: dict[str, Any] | None) -> dict[str, Any]:
    spec = get_by_rule_id(rule_id)
    observation = ledger_item.get("observation") if ledger_item else None
    observation_type = classify_observation_type(observation)
    execution_status = ledger_item.get("status") if ledger_item else None
    return {
        "rule_id": rule_id,
        "rule_name": spec.rule_name if spec else None,
        "dict_code": spec.dict_code if spec else None,
        "procedure_code": spec.procedure_code if spec else None,
        "execution_status": execution_status,
        "finding_count": ledger_item.get("finding_count") if ledger_item else None,
        "has_observation": isinstance(observation, dict),
        "observation_type": observation_type,
        "module": _classify_module(rule_id, spec),
        "next_action": _next_action(execution_status, observation_type),
    }


def _next_action(execution_status: Any, observation_type: str) -> str:
    if execution_status is None:
        return NEXT_ACTION_NOT_EXECUTED
    if execution_status == STATUS_DATA_INSUFFICIENT:
        return NEXT_ACTION_DATA_INSUFFICIENT
    if execution_status != STATUS_EXECUTED:
        return NEXT_ACTION_NOT_EXECUTED
    if observation_type == OBSERVATION_EVIDENCE_LEVEL:
        return NEXT_ACTION_DONE
    return NEXT_ACTION_NEED_HOW


def _classify_module(rule_id: str, spec: RuleSpec | None) -> str:
    procedure_code = spec.procedure_code if spec else None
    if procedure_code == "FA_LIST":
        return "FA list"
    if rule_id == "psp_completion" or procedure_code == "SUMMARY":
        return "PSP"
    if procedure_code == "K.01" or rule_id.startswith("rollforward_"):
        return "K.01"
    if procedure_code in {"K.02.1", "K.02.2"}:
        return procedure_code
    if procedure_code and procedure_code.startswith("K.03"):
        return "K.03"
    if rule_id.startswith("lead_") or rule_id in {
        "materiality_consistency",
        "risk_threshold_consistency",
        "unexpected_movement_investigation",
    }:
        return "Lead"
    return "UNKNOWN"


def _ledger_items(execution_ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(execution_ledger, dict):
        return []
    items = execution_ledger.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
