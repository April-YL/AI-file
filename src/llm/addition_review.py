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

SYSTEM_PROMPT = """你是固定资产审计底稿中 K.02.1 新增测试的语义复核助手。
你只复核文字说明是否充分、是否与已给出的事实一致，不重新做确定性检查。

硬性边界：
1. 不计算、不判断金额是否相符。金额勾稽、抽样总体金额、TE、CRA、样本量、样本匹配都由规则判定。请把 deterministic_rule_findings 当作既定事实。
2. 不改写、不推翻任何规则产生的 FAIL/WARN/NEED_REVIEW。若规则已发现差异，只判断文字是否解释了差异。
3. 不判断发票、合同、验收单等外部证据真伪。
4. 只使用输入中的内容。若证据不足，只返回 unclear 或 insufficient，不要自行补事实。

复核主题：
- waiver_reason：不执行/拒绝执行理由是否具体、是否有可见金额依据、是否只是“低于 TE/SAD”“不重大”“无异常”这类空泛表述。
- sample_selection：抽样/关键项目选择依据是否清楚，是否与 K.02.1a 的 sample_method、关键项目或剩余总体说明一致。不要判断样本量对不对。
- exception_summary：是否有证据支持“无异常”结论，且是否解释了规则发现的差异。
- special_addition_source：非购置新增（如在建工程转入、企业合并、转入、重分类等）是否说明纳入 K.02.1 还是由其他程序处理。不要自己排除金额。
- cross_sheet_explanation：K.02.1 / K.02.1a / 汇总页是否解释了样本池差异、样本不一致、TE/CRA 不一致等规则发现。

常见不足：
1. 只写低于 TE/SAD、不重大、无异常，但没有金额依据或替代程序。
2. 列了样本，却没有说明选择依据。
3. K.02.1 说没有异常，但输入里看不到已测试属性，或者规则仍显示样本/金额差异未解决。
4. 存在非购置新增，但没有说明是否在本程序测试或转到其他底稿。
5. 叙述与 deterministic_rule_findings 相冲突，或没有回应这些差异。

请只返回一个 JSON 对象，不要返回 markdown。"""

USER_TEMPLATE = """请复核 K.02.1 新增测试的语义充分性，并返回 JSON：
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

_TOPIC_LABELS = {
    "waiver_reason": "不执行理由",
    "sample_selection": "样本选择依据",
    "exception_summary": "异常结论",
    "special_addition_source": "特殊新增来源",
    "cross_sheet_explanation": "跨表勾稽说明",
}

_DEFAULT_ACTIONS = {
    "waiver_reason": "补充不执行理由的金额基础、风险判断和替代程序。",
    "sample_selection": "补充关键项目或抽样选择依据，并说明剩余总体为何无需再抽样。",
    "exception_summary": "补充样本差异、属性异常或无异常结论的依据，并回应规则差异。",
    "special_addition_source": "说明非购置新增是否纳入本程序，或索引至其他底稿处理。",
    "cross_sheet_explanation": "补充 K.02.1、K.02.1a、汇总页与规则发现之间的勾稽说明。",
}


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _localized_topic(topic: str) -> str:
    return _TOPIC_LABELS.get(topic, topic)


def _localized_missing_evidence(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items[:5]:
        text = str(item).strip()
        if not text:
            continue
        result.append(text if _has_cjk(text) else "缺少相关依据")
    return result


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
        if topic == "sample_selection":
            continue
        rationale = str(item.get("rationale", "")).strip()
        action = str(item.get("suggested_action", "")).strip()
        missing = item.get("missing_evidence")
        sev = Severity.WARN if assessment == "insufficient" else Severity.NEED_REVIEW
        label = _localized_topic(topic)
        if assessment == "insufficient":
            msg = f"K.02.1 {label}说明不足"
        else:
            msg = f"K.02.1 {label}需人工复核"
        if rationale and _has_cjk(rationale):
            msg += f"：{rationale}"
        missing_text = _localized_missing_evidence(missing)
        if missing_text:
            msg += f"；缺少依据：{', '.join(missing_text)}"

        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=topic,
                severity=sev,
                message=msg,
                suggestion=action if _has_cjk(action) else _DEFAULT_ACTIONS.get(topic, "补充说明并回应规则发现。"),
                procedure_code="K.02.1",
                source_sheet=source_sheet,
                source_row=source_row,
                review_source="LLM辅助判断",
                llm_review_type="K.02.1 新增测试语义复核",
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
