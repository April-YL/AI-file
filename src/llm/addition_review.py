"""K.02.1 addition-test semantic review prompts.

This module is intentionally not wired into the workbook pipeline yet. It defines
the LLM prompt, payload shape, and mock-testable review helpers for future
K.02.1 / K.02.1a semantic checks.
"""

from __future__ import annotations

import json
from typing import Any

from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
)
from ingest.records import FaListDataset
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.models import QcIssue, Severity

RULE_ID = "addition_semantic_review"

SYSTEM_PROMPT = """You are a fixed asset audit K.02.1 addition-test reviewer.
You review only semantic sufficiency and consistency of written explanations.
You must not re-perform deterministic checks.

Hard boundaries:
1. Do not calculate or conclude whether amounts agree. Amount reconciliation,
   sample-pool amount, TE, CRA, sample size, and sample matching are decided by
   rules. Treat deterministic_rule_findings as facts.
2. Do not change or override any FAIL/WARN/NEED_REVIEW from rules. If rules have
   already identified a difference, judge only whether the preparer's narrative
   explains that difference.
3. Do not judge authenticity of invoices, contracts, acceptance reports, or
   other external evidence.
4. Use only the provided payload. If evidence is insufficient, return unclear or
   insufficient; do not invent facts.

Review topics:
- waiver_reason: whether a refusal / non-execution reason is specific, supported
  by visible context, and not merely "below TE/SAD", "immaterial", or "no
  anomaly" without amount basis or alternative procedures.
- sample_selection: whether sample-selection or key-item rationale is clear and
  consistent with K.02.1a sample_method / key item / remaining-population
  narrative. Do not judge whether the sample size is correct.
- exception_summary: whether a "no exception" conclusion is supported by visible
  tested-sample attributes and whether it explains any rule findings.
- special_addition_source: whether non-purchase additions such as construction
  in progress transfer, business combination, transfer-in, reclassification, or
  other special sources are explained as included in K.02.1 or handled by other
  procedures. Do not exclude such amounts yourself.
- cross_sheet_explanation: whether K.02.1 / K.02.1a / summary page narratives
  explain deterministic findings such as sample-pool mismatch, sample mismatch,
  or TE/CRA inconsistency.

Typical insufficient cases:
1. Waiver reason only says below TE/SAD, immaterial, or no exception, with no
   visible amount basis or alternative procedure.
2. Samples are listed but the selection basis is not described.
3. K.02.1 says no exceptions, but the payload shows no tested attributes or rules
   show unresolved sample / amount differences.
4. Non-purchase additions exist but no narrative explains whether they are tested
   here or routed to another workpaper.
5. The narrative contradicts deterministic_rule_findings or does not address
   them.

Return exactly one JSON object. Do not return markdown."""

USER_TEMPLATE = """Review K.02.1 addition-test semantic sufficiency. Return JSON:
{{
  "topics": [
    {{
      "topic": "waiver_reason|sample_selection|exception_summary|special_addition_source|cross_sheet_explanation",
      "assessment": "sufficient|insufficient|unclear",
      "rationale": "",
      "missing_evidence": [],
      "suggested_action": ""
    }}
  ]
}}

Input:
{payload}
"""


def build_addition_review_payload(
    *,
    addition_list: FaListDataset | None = None,
    addition_test: AdditionTestSheetDataset | None = None,
    addition_sample_output: AdditionSampleOutputDataset | None = None,
    addition_execution_path: AdditionExecutionPathDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "addition_list": _addition_list_excerpt(addition_list),
        "addition_execution_path": (
            addition_execution_path.to_dict() if addition_execution_path else None
        ),
        "addition_test": _addition_test_excerpt(addition_test),
        "addition_sample_output": _sample_output_excerpt(addition_sample_output),
        "deterministic_rule_findings": _issue_hints(prior_issues or []),
        "review_policy": {
            "do_not_override_rule_findings": True,
            "amounts_samples_te_cra_are_rules_only": True,
            "llm_reviews_semantic_sufficiency_only": True,
        },
        "workbook_context": workbook_context or {},
    }


def run_addition_llm_review(
    config: LlmConfig,
    *,
    addition_list: FaListDataset | None = None,
    addition_test: AdditionTestSheetDataset | None = None,
    addition_sample_output: AdditionSampleOutputDataset | None = None,
    addition_execution_path: AdditionExecutionPathDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> tuple[list[QcIssue], dict[str, Any] | None]:
    if not config.enabled:
        return [], None
    payload = build_addition_review_payload(
        addition_list=addition_list,
        addition_test=addition_test,
        addition_sample_output=addition_sample_output,
        addition_execution_path=addition_execution_path,
        prior_issues=prior_issues,
        workbook_context=workbook_context,
    )
    user = USER_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False, indent=2))
    try:
        review = chat_completion_json(config, system=SYSTEM_PROMPT, user=user)
    except LlmClientError:
        return [], None
    if not review:
        return [], None
    return _issues_from_review(review, payload), review


def build_addition_llm_issues(
    config: LlmConfig,
    *,
    addition_list: FaListDataset | None = None,
    addition_test: AdditionTestSheetDataset | None = None,
    addition_sample_output: AdditionSampleOutputDataset | None = None,
    addition_execution_path: AdditionExecutionPathDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> list[QcIssue]:
    issues, _ = run_addition_llm_review(
        config,
        addition_list=addition_list,
        addition_test=addition_test,
        addition_sample_output=addition_sample_output,
        addition_execution_path=addition_execution_path,
        prior_issues=prior_issues,
        workbook_context=workbook_context,
    )
    return issues


def _addition_list_excerpt(addition_list: FaListDataset | None) -> dict[str, Any] | None:
    if addition_list is None:
        return None
    methods: dict[str, int] = {}
    for record in addition_list.records:
        method = str(getattr(record, "addition_method", "") or "").strip() or "(blank)"
        methods[method] = methods.get(method, 0) + 1
    return {
        "source_sheet": addition_list.source_sheet,
        "record_count": len(addition_list.records),
        "addition_methods": methods,
        "mapped_fields": [m.standard_field for m in addition_list.mapped_fields],
    }


def _addition_test_excerpt(
    addition_test: AdditionTestSheetDataset | None,
) -> dict[str, Any] | None:
    if addition_test is None:
        return None
    return {
        "source_sheet": addition_test.source_sheet,
        "waiver_note_text": addition_test.waiver_note_text,
        "waiver_note_rows": addition_test.waiver_note_rows,
        "amounts": {k: v.to_dict() for k, v in addition_test.amounts.items()},
        "tested_sample_count": len(addition_test.tested_samples),
        "tested_samples": [s.to_dict() for s in addition_test.tested_samples[:20]],
        "module_assessments": [m.to_dict() for m in addition_test.module_assessments],
        "recognition_confidence": addition_test.recognition_confidence,
        "notes": addition_test.notes,
    }


def _sample_output_excerpt(
    sample_output: AdditionSampleOutputDataset | None,
) -> dict[str, Any] | None:
    if sample_output is None:
        return None
    return {
        "source_sheet": sample_output.source_sheet,
        "parameters": {k: v.to_dict() for k, v in sample_output.parameters.items()},
        "amounts": {k: v.to_dict() for k, v in sample_output.amounts.items()},
        "selected_sample_count": len(sample_output.selected_samples),
        "selected_samples": [s.to_dict() for s in sample_output.selected_samples[:20]],
        "module_assessments": [m.to_dict() for m in sample_output.module_assessments],
        "recognition_confidence": sample_output.recognition_confidence,
        "notes": sample_output.notes,
    }


def _issue_hints(issues: list[QcIssue]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for issue in issues:
        hints.append(
            {
                "rule_id": issue.rule_id,
                "field": issue.field,
                "severity": issue.severity.value,
                "procedure_code": issue.procedure_code,
                "message": issue.message,
            }
        )
    return hints[:20]


def _issues_from_review(review: dict[str, Any], payload: dict[str, Any]) -> list[QcIssue]:
    raw_topics = review.get("topics") if isinstance(review.get("topics"), list) else []
    issues: list[QcIssue] = []
    source_sheet = _source_sheet(payload)
    source_row = _source_row(payload)
    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        assessment = str(item.get("assessment", "")).strip().lower()
        if assessment == "sufficient":
            continue
        topic = str(item.get("topic", "addition_semantic")).strip() or "addition_semantic"
        rationale = str(item.get("rationale", "")).strip()
        action = str(item.get("suggested_action", "")).strip()
        missing = item.get("missing_evidence")
        sev = Severity.WARN if assessment == "insufficient" else Severity.NEED_REVIEW
        if assessment == "insufficient":
            msg = f"K.02.1 {topic}: semantic explanation is insufficient"
        else:
            msg = f"K.02.1 {topic}: semantic explanation needs manual review"
        if rationale:
            msg += f" ({rationale})"
        if isinstance(missing, list) and missing:
            msg += f"; missing evidence: {', '.join(str(x) for x in missing[:5])}"

        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=topic,
                severity=sev,
                message=msg,
                suggestion=action
                or "Supplement the explanation and cross-reference visible support; rules findings must not be overridden.",
                procedure_code="K.02.1",
                source_sheet=source_sheet,
                source_row=source_row,
                review_source="LLM assisted judgment",
                llm_review_type="K.02.1 addition semantic sufficiency",
            )
        )
    return issues


def _source_sheet(payload: dict[str, Any]) -> str:
    for key in ("addition_test", "addition_sample_output", "addition_list"):
        value = payload.get(key)
        if isinstance(value, dict) and value.get("source_sheet"):
            return str(value["source_sheet"])
    return "K.02.1"


def _source_row(payload: dict[str, Any]) -> int | None:
    execution = payload.get("addition_execution_path")
    if isinstance(execution, dict):
        row = execution.get("summary_source_row")
        if isinstance(row, int):
            return row
    test = payload.get("addition_test")
    if isinstance(test, dict):
        rows = test.get("waiver_note_rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], int):
            return rows[0]
    return None
