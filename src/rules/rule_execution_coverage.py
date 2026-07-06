from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from rules.addition_runner import ADDITION_RULE_IDS
from rules.disposal_runner import DISPOSAL_RULE_IDS
from rules.how_coverage_diagnostics import (
    OBSERVATION_EVIDENCE_LEVEL,
    OBSERVATION_LEGACY,
    OBSERVATION_MISSING,
    classify_observation_type,
    default_runner_ledger_rule_ids,
)
from rules.k03_runner import K03_RULE_IDS
from rules.lead_runner import LEAD_RULE_IDS
from rules.registry import RuleSpec, get_by_rule_id, iter_implemented
from rules.rollforward_runner import ROLLFORWARD_RULE_IDS
from rules.runner import FA_LIST_RULE_IDS

EXECUTION_EXECUTED = "EXECUTED"
EXECUTION_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
EXECUTION_NOT_APPLICABLE = "NOT_APPLICABLE"
EXECUTION_NOT_TRIGGERED_BY_CONTEXT = "NOT_TRIGGERED_BY_CONTEXT"
EXECUTION_LLM_DISABLED = "LLM_DISABLED"
EXECUTION_DELIVERY_CONTEXT_MISSING = "DELIVERY_CONTEXT_MISSING"
EXECUTION_NOT_WIRED = "NOT_WIRED"
EXECUTION_UNKNOWN = "UNKNOWN"

HOW_EVIDENCE_LEVEL = OBSERVATION_EVIDENCE_LEVEL
HOW_LEGACY = OBSERVATION_LEGACY
HOW_MISSING = OBSERVATION_MISSING
HOW_NOT_APPLICABLE = "NOT_APPLICABLE"

_LEDGER_NOT_APPLICABLE = "NOT_APPLICABLE"

_LLM_RULE_IDS = {
    "addition_semantic_review",
    "disposal_semantic_review",
    "lead_expectation_semantic",
    "lead_fluctuation_notes_semantic",
    "lead_adjustment_layout_review",
    "lead_adjustment_semantic",
    "rollforward_notes_semantic",
}

_DELIVERY_RULE_IDS = {"first_delivery_standard", "final_delivery_standard"}
_RUNTIME_GUARDRAIL_RULE_IDS = {"lead_ingest_readability"}

_LEAD_ONLY_RULE_IDS = set(LEAD_RULE_IDS) | {
    "lead_expectation_semantic",
    "lead_fluctuation_notes_semantic",
    "lead_adjustment_layout_review",
    "lead_adjustment_semantic",
}

_EXECUTION_STATUS_LABELS = {
    EXECUTION_EXECUTED: "已执行",
    EXECUTION_DATA_INSUFFICIENT: "资料不足，未能完整执行",
    EXECUTION_NOT_APPLICABLE: "本次不适用",
    EXECUTION_NOT_TRIGGERED_BY_CONTEXT: "未识别到对应底稿，未进入执行",
    EXECUTION_LLM_DISABLED: "LLM 未开启，语义复核未执行",
    EXECUTION_DELIVERY_CONTEXT_MISSING: "未传入交付阶段信息，交付检查未执行",
    EXECUTION_NOT_WIRED: "规则已登记但未接入执行",
    EXECUTION_UNKNOWN: "原因待确认",
}

_TRACE_LABELS = {
    HOW_EVIDENCE_LEVEL: "可查看取数与判断说明",
    HOW_LEGACY: "可查看基础执行说明",
    HOW_MISSING: "暂无取数与判断说明",
    HOW_NOT_APPLICABLE: "不适用",
}


def build_rule_execution_coverage_matrix(
    execution_ledger: dict[str, Any] | None,
    *,
    workbook_context: Any | None = None,
    llm_enabled: bool = False,
    delivery_context: Any | None = None,
    runner_rule_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a read-only matrix explaining where each rule went in this run.

    This does not decide whether a rule should have been executed for audit
    purposes. It only classifies observable runtime facts from registry, runner
    ids, ledger, LLM setting, delivery context, and workbook context.
    """

    runner_ids = set(
        default_runner_ledger_rule_ids()
        if runner_rule_ids is None
        else runner_rule_ids
    )
    implemented_specs = list(iter_implemented())
    implemented_ids = {spec.rule_id for spec in implemented_specs}
    ledger_items = _ledger_items(execution_ledger)
    item_by_rule_id = {
        str(item.get("rule_id")): item
        for item in ledger_items
        if item.get("rule_id") is not None
    }
    row_rule_ids = _dedupe((*implemented_ids, *runner_ids, *item_by_rule_id.keys()))
    category_by_rule_id = {
        rule_id: _classify_matrix_category(rule_id, implemented_ids)
        for rule_id in row_rule_ids
    }
    rows = [
        _build_matrix_row(
            rule_id,
            item_by_rule_id.get(rule_id),
            matrix_category=category_by_rule_id[rule_id],
            runner_ids=runner_ids,
            workbook_context=workbook_context,
            llm_enabled=llm_enabled,
            delivery_context=delivery_context,
        )
        for rule_id in row_rule_ids
    ]
    status_counts = Counter(row["execution_status"] for row in rows)
    how_counts = Counter(row["how_status"] for row in rows)
    ledger_rows = [row for row in rows if row["rule_id"] in item_by_rule_id]
    ledger_status_counts = Counter(row["execution_status"] for row in ledger_rows)
    ledger_how_counts = Counter(row["how_status"] for row in ledger_rows)
    return {
        "summary": {
            "registry_implemented_rule_count": len(implemented_ids),
            "matrix_rule_count": len(rows),
            "matrix_category_counts": dict(Counter(category_by_rule_id.values())),
            "implemented_rule_count": sum(
                1 for category in category_by_rule_id.values() if category == "implemented_rules"
            ),
            "delivery_check_count": sum(
                1 for category in category_by_rule_id.values() if category == "delivery_checks"
            ),
            "delivery_check_ids": sorted(
                rule_id
                for rule_id, category in category_by_rule_id.items()
                if category == "delivery_checks"
            ),
            "runtime_guardrail_count": sum(
                1 for category in category_by_rule_id.values() if category == "runtime_guardrails"
            ),
            "runtime_guardrail_ids": sorted(
                rule_id
                for rule_id, category in category_by_rule_id.items()
                if category == "runtime_guardrails"
            ),
            "ledger_recorded_rule_count": len(item_by_rule_id),
            "executed_or_recorded_rule_count": len(item_by_rule_id),
            "execution_status_counts": dict(status_counts),
            "ledger_status_counts": dict(ledger_status_counts),
            "how_status_counts": dict(how_counts),
            "ledger_how_status_counts": dict(ledger_how_counts),
            "ledger_legacy_count": sum(1 for row in ledger_rows if row["how_status"] == HOW_LEGACY),
            "ledger_missing_how_count": sum(1 for row in ledger_rows if row["how_status"] == HOW_MISSING),
            # Backward-compatible names from v0. They mean ledger-recorded rules,
            # not only EXECUTED rules.
            "executed_legacy_count": sum(1 for row in ledger_rows if row["how_status"] == HOW_LEGACY),
            "executed_missing_how_count": sum(1 for row in ledger_rows if row["how_status"] == HOW_MISSING),
        },
        "rules": rows,
    }


def _build_matrix_row(
    rule_id: str,
    ledger_item: dict[str, Any] | None,
    *,
    matrix_category: str,
    runner_ids: set[str],
    workbook_context: Any | None,
    llm_enabled: bool,
    delivery_context: Any | None,
) -> dict[str, Any]:
    spec = get_by_rule_id(rule_id)
    if ledger_item is not None:
        execution_status, reason, basis = _status_from_ledger(ledger_item)
        how_status = _how_status_for_ledger(ledger_item)
    else:
        execution_status, reason, basis = _status_for_missing_ledger(
            rule_id,
            spec,
            runner_ids=runner_ids,
            workbook_context=workbook_context,
            llm_enabled=llm_enabled,
            delivery_context=delivery_context,
        )
        how_status = HOW_NOT_APPLICABLE

    observation = ledger_item.get("observation") if ledger_item else None
    finding_count = _finding_count(ledger_item)
    return {
        "rule_id": rule_id,
        "rule_code": spec.dict_code if spec else rule_id,
        "rule_name": spec.rule_name if spec else None,
        "module": _classify_module(rule_id, spec),
        "matrix_category": matrix_category,
        "execution_status": execution_status,
        "execution_status_label": _execution_status_label(execution_status),
        "non_execution_reason": reason,
        "finding_count": finding_count,
        "how_status": how_status,
        "source_summary": _source_summary(observation),
        "trace_label": _trace_label(how_status),
        "trace_detail": _trace_detail(observation, note=reason),
        "evidence_basis": basis,
        "next_action": _next_action(execution_status, how_status),
    }


def _execution_status_label(status: str) -> str:
    return _EXECUTION_STATUS_LABELS.get(status, _EXECUTION_STATUS_LABELS[EXECUTION_UNKNOWN])


def _trace_label(how_status: str) -> str:
    return _TRACE_LABELS.get(how_status, "暂无取数与判断说明")


def _finding_count(item: dict[str, Any] | None) -> int | None:
    if item is None:
        return None
    try:
        return int(item.get("finding_count") or 0)
    except (TypeError, ValueError):
        return 0


def _trace_detail(observation: Any, *, note: str | None = None) -> dict[str, Any]:
    if not isinstance(observation, dict):
        return {
            "checked_materials": [],
            "source_locations": [],
            "values_read": [],
            "check_method": "",
            "expected_result": "",
            "actual_result": "",
            "missing_data": [],
            "notes": note or "",
        }
    if _is_evidence_observation(observation):
        checked_data = observation.get("checked_data") or []
        materials: list[str] = []
        locations: list[str] = []
        values_read: list[dict[str, Any]] = []
        missing: list[str] = []
        if isinstance(checked_data, list):
            for raw in checked_data:
                if not isinstance(raw, dict):
                    continue
                material = _join_non_empty(raw.get("sheet"), raw.get("section"), sep=" / ")
                if material:
                    materials.append(material)
                location = _join_non_empty(raw.get("sheet"), raw.get("location"), sep="!")
                if location:
                    locations.append(location)
                raw_missing = raw.get("missing_data") or []
                if isinstance(raw_missing, list):
                    missing.extend(str(v) for v in raw_missing if str(v).strip())
                raw_values = raw.get("values_read") or []
                if isinstance(raw_values, list):
                    for value in raw_values:
                        if isinstance(value, dict):
                            values_read.append(
                                {
                                    "label": value.get("label") or "",
                                    "value": value.get("value") or "",
                                    "row": value.get("row") or "",
                                    "column": value.get("column") or "",
                                    "cell": value.get("cell") or "",
                                    "unit": value.get("unit") or "",
                                    "amount_type": value.get("amount_type") or "",
                                }
                            )
        return {
            "checked_materials": _dedupe_text(materials),
            "source_locations": _dedupe_text(locations),
            "values_read": values_read,
            "check_method": observation.get("check_logic") or "",
            "expected_result": observation.get("expected_result") or "",
            "actual_result": observation.get("actual_result")
            or observation.get("result_summary")
            or "",
            "missing_data": _dedupe_text(missing),
            "notes": note or observation.get("notes") or "",
        }
    return {
        "checked_materials": _legacy_inputs(observation),
        "source_locations": _legacy_locations(observation),
        "values_read": [],
        "check_method": _legacy_check_method(observation),
        "expected_result": "",
        "actual_result": "",
        "missing_data": [],
        "notes": note or str(observation.get("notes") or ""),
    }


def _source_summary(observation: Any) -> str:
    detail = _trace_detail(observation)
    materials = detail.get("checked_materials") or []
    locations = detail.get("source_locations") or []
    if materials:
        return "；".join(str(v) for v in materials[:3])
    if locations:
        return "；".join(str(v) for v in locations[:3])
    return "—"


def _is_evidence_observation(observation: dict[str, Any]) -> bool:
    return {
        "checked_data",
        "check_logic",
        "expected_result",
        "actual_result",
        "result_summary",
    }.issubset(set(observation))


def _legacy_inputs(observation: dict[str, Any]) -> list[str]:
    inputs = observation.get("inputs") or []
    if not isinstance(inputs, list):
        return []
    result: list[str] = []
    for raw in inputs:
        if not isinstance(raw, dict):
            continue
        result.append(
            _join_non_empty(
                raw.get("source_sheet"),
                raw.get("section"),
                raw.get("field"),
                sep=" / ",
            )
        )
    return _dedupe_text(result)


def _legacy_locations(observation: dict[str, Any]) -> list[str]:
    inputs = observation.get("inputs") or []
    if not isinstance(inputs, list):
        return []
    result: list[str] = []
    for raw in inputs:
        if not isinstance(raw, dict):
            continue
        row = raw.get("row")
        column = raw.get("column")
        cell_range = raw.get("range")
        result.append(
            _join_non_empty(
                raw.get("source_sheet"),
                f"row {row}" if row else "",
                f"col {column}" if column else "",
                cell_range,
                sep=" / ",
            )
        )
    return _dedupe_text(result)


def _legacy_check_method(observation: dict[str, Any]) -> str:
    checks = observation.get("checks") or []
    if not isinstance(checks, list):
        return ""
    parts: list[str] = []
    for raw in checks:
        if isinstance(raw, dict):
            parts.append(_join_non_empty(raw.get("name"), raw.get("operator"), raw.get("result"), sep=" "))
    return "；".join(_dedupe_text(parts))


def _join_non_empty(*values: Any, sep: str) -> str:
    return sep.join(str(value).strip() for value in values if str(value or "").strip())


def _dedupe_text(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _classify_matrix_category(rule_id: str, implemented_ids: set[str]) -> str:
    if rule_id in implemented_ids:
        return "implemented_rules"
    if rule_id in _DELIVERY_RULE_IDS:
        return "delivery_checks"
    if rule_id in _RUNTIME_GUARDRAIL_RULE_IDS:
        return "runtime_guardrails"
    return "other_runtime_observations"


def _status_from_ledger(item: dict[str, Any]) -> tuple[str, str | None, str]:
    status = item.get("status")
    note = str(item.get("status_note") or "").strip() or None
    if status == EXECUTION_EXECUTED:
        return EXECUTION_EXECUTED, None, "execution ledger records EXECUTED"
    if status == EXECUTION_DATA_INSUFFICIENT:
        return EXECUTION_DATA_INSUFFICIENT, note or "ledger records data insufficient", "execution ledger status_note"
    if status == _LEDGER_NOT_APPLICABLE:
        return (
            EXECUTION_NOT_APPLICABLE,
            note or "ledger records not applicable for this run",
            "execution ledger records NOT_APPLICABLE",
        )
    return EXECUTION_UNKNOWN, note or f"ledger status is {status}", "execution ledger status is not recognized by matrix"


def _status_for_missing_ledger(
    rule_id: str,
    spec: RuleSpec | None,
    *,
    runner_ids: set[str],
    workbook_context: Any | None,
    llm_enabled: bool,
    delivery_context: Any | None,
) -> tuple[str, str, str]:
    if rule_id in _DELIVERY_RULE_IDS and delivery_context is None:
        return (
            EXECUTION_DELIVERY_CONTEXT_MISSING,
            "本次没有传入交付阶段，因此交付检查未进入执行",
            "delivery_context is None",
        )
    if rule_id in _LLM_RULE_IDS and not llm_enabled:
        return (
            EXECUTION_LLM_DISABLED,
            "本次 LLM 未开启，因此语义复核规则未进入执行",
            "llm_enabled is False",
        )
    if rule_id not in runner_ids and rule_id not in _LLM_RULE_IDS:
        return (
            EXECUTION_NOT_WIRED,
            "规则已登记，但当前 runner 可记录清单未包含该规则",
            "registry implemented rule is absent from runner rule ids",
        )

    context_status = _status_from_workbook_context(rule_id, workbook_context)
    if context_status is not None:
        return context_status

    return (
        EXECUTION_UNKNOWN,
        "现有诊断信息不足，不能稳定判断该规则本次为什么未进入执行",
        "no matching ledger item and no stable context signal",
    )


def _status_from_workbook_context(
    rule_id: str,
    workbook_context: Any | None,
) -> tuple[str, str, str] | None:
    if workbook_context is None:
        return None
    if rule_id in FA_LIST_RULE_IDS and getattr(workbook_context, "fa_list", None) is None:
        return _not_triggered("未识别到 FA list，因此 FA list 规则未进入执行", "workbook_context.fa_list is None")
    if rule_id in ROLLFORWARD_RULE_IDS and getattr(workbook_context, "rollforward", None) is None:
        return _not_triggered("未识别到 K.01 后推表，因此 K.01 规则未进入执行", "workbook_context.rollforward is None")
    if rule_id in ADDITION_RULE_IDS and getattr(workbook_context, "addition_list", None) is None:
        return _not_triggered("未识别到新增清单，因此 K.02.1 新增规则未进入执行", "workbook_context.addition_list is None")
    if rule_id in DISPOSAL_RULE_IDS and _missing_all(
        workbook_context,
        ("disposal_list", "disposal_test", "disposal_sample_output", "disposal_execution_path"),
    ):
        return _not_triggered("未识别到处置测试相关资料，因此 K.02.2 规则未进入执行", "disposal context objects are all None")
    if rule_id in K03_RULE_IDS and not getattr(workbook_context, "k03_sheets", None):
        return _not_triggered("未识别到 K.03 折旧测试资料，因此 K.03 规则未进入执行", "workbook_context.k03_sheets is empty")
    if rule_id in _LEAD_ONLY_RULE_IDS and getattr(workbook_context, "lead", None) is None:
        return _not_triggered("未识别到 K.00 Lead，因此 Lead 规则未进入执行", "workbook_context.lead is None")
    if rule_id in {"addition_test_package_complete"} and _missing_all(
        workbook_context,
        ("summary", "addition_test", "addition_list", "addition_sample_output"),
    ):
        return _not_triggered("未识别到新增测试入口资料，因此新增测试程序包规则未进入执行", "addition package context objects are all None")
    if rule_id in {"disposal_test_package_complete"} and _missing_all(
        workbook_context,
        ("summary", "disposal_test", "disposal_list", "disposal_sample_output"),
    ):
        return _not_triggered("未识别到处置测试入口资料，因此处置测试程序包规则未进入执行", "disposal package context objects are all None")
    if rule_id == "psp_completion" and getattr(workbook_context, "summary", None) is None:
        return _not_triggered("未识别到汇总页，因此 PSP 执行完整性规则未进入执行", "workbook_context.summary is None")
    return None


def _not_triggered(reason: str, basis: str) -> tuple[str, str, str]:
    return EXECUTION_NOT_TRIGGERED_BY_CONTEXT, reason, basis


def _missing_all(workbook_context: Any, fields: Sequence[str]) -> bool:
    return all(getattr(workbook_context, field, None) in (None, []) for field in fields)


def _how_status_for_ledger(item: dict[str, Any]) -> str:
    observation = item.get("observation")
    observation_type = classify_observation_type(observation)
    if observation_type == OBSERVATION_EVIDENCE_LEVEL:
        return HOW_EVIDENCE_LEVEL
    if observation_type == OBSERVATION_LEGACY:
        return HOW_LEGACY
    return HOW_MISSING


def _next_action(execution_status: str, how_status: str) -> str:
    if execution_status == EXECUTION_EXECUTED and how_status == HOW_EVIDENCE_LEVEL:
        return "DONE"
    if execution_status in {
        EXECUTION_EXECUTED,
        EXECUTION_DATA_INSUFFICIENT,
        EXECUTION_NOT_APPLICABLE,
    } and how_status != HOW_EVIDENCE_LEVEL:
        return "NEED_HOW"
    if execution_status == EXECUTION_NOT_WIRED:
        return "CHECK_RUNNER_WIRING"
    if execution_status == EXECUTION_UNKNOWN:
        return "REVIEW_CAUSE"
    return "EXPLAINED_NOT_EXECUTED"


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
