from __future__ import annotations

import re
from collections import Counter

from ingest.k03_sheet import (
    COMPONENT_STATE_AMBIGUOUS,
    COMPONENT_STATE_EXECUTED,
    COMPONENT_STATE_INCOMPLETE,
    COMPONENT_STATE_TEMPLATE_ONLY,
    K03ComponentSheet,
    K03ExecutionProfile,
)
from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.models import QcIssue, Severity
from rules.psp_completion import normalize_execution_status

RULE_IDS = (
    "k03_program_execution_consistency",
    "k03_depreciation_path_identified",
    "k03_path_combination_consistency",
)
_KINDS = ("sap", "tod", "policy")
_DEP_ROLES = ("sap_medium", "sap_high", "tod_by_item", "tod_sampling")
_ROLE_LABELS = {
    "sap_medium": "SAP medium",
    "sap_high": "SAP high",
    "tod_by_item": "TOD by-item",
    "tod_sampling": "TOD sampling",
}


def run_k03_execution_control(
    summary: SummarySheetDataset | None,
    profile: K03ExecutionProfile | None,
    *,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    """Check K.03 routing from the parsed summary and execution profile only."""
    recorder = recorder or RuleExecutionRecorder()
    rows = _group_rows(summary)
    issues = _program_consistency(summary, profile, rows, recorder)
    issues.extend(_path_identified(summary, profile, rows, recorder))
    issues.extend(_path_combination(summary, profile, rows, recorder))
    return issues


def _program_consistency(summary, profile, rows, recorder) -> list[QcIssue]:
    rule_id = RULE_IDS[0]
    if summary is None or profile is None:
        note = "Summary dataset or K.03 execution profile is unavailable."
        _record_missing(recorder, rule_id, summary, profile, rows, note)
        return []
    actual = {
        "sap": _has_executed(profile, ("sap_medium", "sap_high")),
        "tod": _has_executed(profile, ("tod_by_item", "tod_sampling")),
        "policy": _has_executed(profile, ("policy_review",)),
    }
    uncertain = {
        "sap": _has_uncertain(profile, ("sap_medium", "sap_high", "unknown_depreciation_test")),
        "tod": _has_uncertain(profile, ("tod_by_item", "tod_sampling", "tod_sampling_output", "unknown_depreciation_test")) or _has_orphan_sampling_output(profile),
        "policy": _has_uncertain(profile, ("policy_review",)),
    }
    issues: list[QcIssue] = []
    missing: list[str] = []
    comparable = 0
    for kind in _KINDS:
        kind_rows = rows[kind]
        if not kind_rows:
            if actual[kind]:
                comparable += 1
                issues.append(_issue(summary, None, kind, "An EXECUTED component exists, but the corresponding summary row is missing."))
            else:
                missing.append(f"No summary row identified for K.03 {kind}.")
            continue
        statuses = {normalize_execution_status(row.execution_status) for row in kind_rows}
        definite = statuses & {"yes", "no"}
        if definite == {"yes", "no"}:
            comparable += 1
            issues.append(_issue(summary, kind_rows[0], kind, "Summary rows contain conflicting yes/no statuses."))
            continue
        if len(definite) != 1:
            missing.append(f"Summary status for K.03 {kind} is missing, partial, or ambiguous.")
            continue
        if statuses - {"yes", "no"}:
            missing.append(f"Additional K.03 {kind} summary row has a missing, partial, or ambiguous status.")
        comparable += 1
        stated = next(iter(definite)) == "yes"
        if not stated and not actual[kind] and uncertain[kind]:
            comparable -= 1
            missing.append(f"Actual execution state for K.03 {kind} is incomplete or ambiguous.")
            continue
        if stated != actual[kind]:
            detail = (
                "Summary states executed, but no EXECUTED component was identified."
                if stated else
                "Summary states not executed, but an EXECUTED component was identified."
            )
            issues.append(_issue(summary, kind_rows[0], kind, detail))
    note = f"Compared {comparable} K.03 summary status(es) with profile components."
    obs = _observation(summary, profile, rows, rule_id, note, missing)
    if issues:
        recorder.record_executed(rule_id, len(issues), note=note, observation=obs)
    elif missing:
        recorder.record_data_insufficient(rule_id, note)
        recorder.record_observation(rule_id, obs)
    elif comparable:
        recorder.record_executed(rule_id, 0, note=note, observation=obs)
    else:
        recorder.record_data_insufficient(rule_id, note)
        recorder.record_observation(rule_id, obs)
    return issues


def _path_identified(summary, profile, rows, recorder) -> list[QcIssue]:
    rule_id = RULE_IDS[1]
    statuses = {kind: _single_status(rows[kind]) for kind in ("sap", "tod")}
    note = "Checked that a selected depreciation test has an EXECUTED SAP or TOD path."
    if summary is None or profile is None or all(value is None for value in statuses.values()):
        _record_missing(recorder, rule_id, summary, profile, rows, note)
        return []
    if statuses == {"sap": "no", "tod": "no"}:
        recorder.record_not_applicable(rule_id, "Summary states that neither SAP nor TOD was executed.")
        recorder.record_observation(rule_id, _observation(summary, profile, rows, rule_id, note, []))
        return []
    if "yes" not in statuses.values():
        _record_missing(recorder, rule_id, summary, profile, rows, "SAP/TOD summary selection is incomplete or ambiguous.")
        return []
    if not _executed(profile, _DEP_ROLES):
        _record_missing(recorder, rule_id, summary, profile, rows, "Summary requires a depreciation test, but no EXECUTED path was identified.")
        return []
    recorder.record_executed(rule_id, 0, note=note, observation=_observation(summary, profile, rows, rule_id, note, []))
    return []


def _path_combination(summary, profile, rows, recorder) -> list[QcIssue]:
    rule_id = RULE_IDS[2]
    note = "Checked path combinations; one SAP plus one TOD path is allowed."
    if profile is None:
        _record_missing(recorder, rule_id, summary, profile, rows, note)
        return []
    executed = _executed(profile, _DEP_ROLES)
    counts = Counter(item.role for item in executed)
    conflicts = [
        f"Multiple EXECUTED sheets were identified for {_ROLE_LABELS[role]}: {_sheet_names(executed, role)}."
        for role, count in counts.items() if count > 1
    ]
    if counts["sap_medium"] and counts["sap_high"]:
        conflicts.append(
            f"Both SAP medium ({_sheet_names(executed, 'sap_medium')}) and SAP high ({_sheet_names(executed, 'sap_high')}) were executed."
        )
    if counts["tod_by_item"] and counts["tod_sampling"]:
        conflicts.append(
            f"Both TOD by-item ({_sheet_names(executed, 'tod_by_item')}) and TOD sampling ({_sheet_names(executed, 'tod_sampling')}) were executed."
        )
    if conflicts:
        issue = QcIssue(
            asset_id=None,
            rule_id=rule_id,
            field="execution_path_combination",
            severity=Severity.NEED_REVIEW,
            message="K.03 has a conflicting depreciation-test path combination: " + " ".join(conflicts),
            suggestion="Confirm the intended execution path and retain only the applicable completed path(s), or document why multiple paths were required.",
            procedure_code="K.03",
            source_sheet=summary.source_sheet if summary else "K.03",
        )
        recorder.record_executed(rule_id, 1, note=note, observation=_observation(summary, profile, rows, rule_id, " ".join(conflicts), []))
        return [issue]
    uncertain = _uncertain(profile)
    statuses = {kind: _single_status(rows[kind]) for kind in ("sap", "tod")}
    if not executed and not uncertain and statuses == {"sap": "no", "tod": "no"}:
        recorder.record_not_applicable(rule_id, "Summary states that neither SAP nor TOD was executed, and no actual path was identified.")
        recorder.record_observation(rule_id, _observation(summary, profile, rows, rule_id, note, []))
        return []
    if not executed or uncertain:
        missing = ["No EXECUTED depreciation-test path was identified."] if not executed else []
        missing.extend(f"Unresolved path: {item.role}/{item.sheet_name}/{item.execution_state}." for item in uncertain)
        recorder.record_data_insufficient(rule_id, note)
        recorder.record_observation(rule_id, _observation(summary, profile, rows, rule_id, note, missing))
        return []
    recorder.record_executed(rule_id, 0, note=note, observation=_observation(summary, profile, rows, rule_id, note, []))
    return []


def _group_rows(summary):
    grouped = {kind: [] for kind in _KINDS}
    if summary:
        for row in summary.programs:
            kind = _program_kind(row)
            if kind:
                grouped[kind].append(row)
    return grouped


def _program_kind(row: PspProgramRow) -> str | None:
    raw = " ".join(filter(None, (row.procedure_name, row.sheet_ref))).lower()
    compact = re.sub(r"[\s._-]+", "", raw)
    if "k032a" in compact:
        return None
    if "k033" in compact:
        return "policy"
    if "k031" in compact:
        return "sap"
    if "k032" in compact:
        return "tod"
    depreciation = "折旧" in raw or "depreciation" in raw
    if depreciation and ("policy" in raw or "政策" in raw):
        return "policy"
    if depreciation and re.search(r"\bsap\b", raw):
        return "sap"
    if depreciation and (re.search(r"\btod\b", raw) or "by item" in raw or "by-item" in raw):
        return "tod"
    return None


def _single_status(rows):
    if not rows:
        return None
    statuses = {normalize_execution_status(row.execution_status) for row in rows}
    definite = statuses & {"yes", "no"}
    return next(iter(definite)) if len(definite) == 1 else None


def _executed(profile, roles):
    return [item for role in roles for item in profile.component_sheets.get(role, []) if item.execution_state == COMPONENT_STATE_EXECUTED]


def _has_executed(profile, roles):
    return bool(_executed(profile, roles))


def _has_uncertain(profile, roles):
    return any(
        item.execution_state in {COMPONENT_STATE_INCOMPLETE, COMPONENT_STATE_AMBIGUOUS}
        for role in roles for item in profile.component_sheets.get(role, [])
    )


def _has_orphan_sampling_output(profile):
    outputs = profile.component_sheets.get("tod_sampling_output", [])
    return bool(
        any(item.execution_state != COMPONENT_STATE_TEMPLATE_ONLY for item in outputs)
        and not _has_executed(profile, ("tod_sampling",))
    )


def _sheet_names(components, role):
    return ", ".join(item.sheet_name for item in components if item.role == role)


def _uncertain(profile) -> list[K03ComponentSheet]:
    result = [
        item
        for role in (*_DEP_ROLES, "unknown_depreciation_test")
        for item in profile.component_sheets.get(role, [])
        if item.execution_state in {COMPONENT_STATE_INCOMPLETE, COMPONENT_STATE_AMBIGUOUS}
        or (role == "unknown_depreciation_test" and item.execution_state != COMPONENT_STATE_TEMPLATE_ONLY)
    ]
    if profile.component_sheets.get("tod_sampling_output") and not _has_executed(profile, ("tod_sampling",)):
        result.extend(item for item in profile.component_sheets["tod_sampling_output"] if item.execution_state != COMPONENT_STATE_TEMPLATE_ONLY)
    return result


def _issue(summary, row, kind, detail):
    return QcIssue(
        asset_id=None,
        rule_id=RULE_IDS[0],
        field=f"{kind}_execution_status",
        severity=Severity.NEED_REVIEW,
        message=f"K.03 {kind} execution status is inconsistent. {detail}",
        suggestion="Reconcile the summary selection to the completed K.03 workpaper and document the final execution path.",
        procedure_code="K.03",
        source_sheet=summary.source_sheet,
        source_row=row.source_row if row else None,
    )


def _record_missing(recorder, rule_id, summary, profile, rows, note):
    recorder.record_data_insufficient(rule_id, note)
    recorder.record_observation(rule_id, _observation(summary, profile, rows, rule_id, note, [note]))


def _observation(summary, profile, rows, rule_id, result, missing):
    summary_values = [{
        "label": f"{kind}: {row.procedure_name}", "value": row.execution_status,
        "row": row.source_row, "column": None, "cell": None, "unit": None,
        "amount_type": "execution_status",
    } for kind in _KINDS for row in rows[kind]][:20]
    component_values = [{
        "label": f"{item.role} / {item.sheet_name}", "value": item.execution_state,
        "row": None, "column": None, "cell": None, "unit": None,
        "amount_type": "execution_state",
    } for items in (profile.component_sheets.values() if profile else []) for item in items][:20]
    return {
        "checked_data": [
            {
                "sheet": summary.source_sheet if summary else None,
                "section": "Summary K.03 program status", "location": None,
                "identified_by": {"sheet_name": summary.source_sheet if summary else None, "section": "Summary K.03 program status", "matched_keywords": ["K.03.1", "K.03.2", "K.03.3"], "matched_rows": [row.source_row for kind in _KINDS for row in rows[kind]][:12], "matched_columns": []},
                "key_columns": ["procedure_name", "sheet_ref", "execution_status"],
                "values_read": summary_values, "missing_data": missing[:12],
            },
            {
                "sheet": None, "section": "K03ExecutionProfile components", "location": None,
                "identified_by": {"sheet_name": None, "section": "K03ExecutionProfile components", "matched_keywords": list(profile.component_sheets)[:12] if profile else [], "matched_rows": [], "matched_columns": []},
                "key_columns": ["role", "sheet_name", "execution_state"],
                "values_read": component_values,
                "missing_data": ["K.03 execution profile is unavailable."] if profile is None else [],
            },
        ],
        "check_logic": "Compare summary K.03 selections with EXECUTED profile components and validate the allowed path combination.",
        "expected_result": "Summary agrees with executed components; one SAP plus one TOD is allowed; policy is assessed separately.",
        "actual_result": result,
        "result_summary": f"{rule_id}: {result}",
    }
