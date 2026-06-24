"""K.02.2 disposal-test semantic review."""

from __future__ import annotations

import json
from typing import Any

from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalSampleOutputDataset,
    DisposalTestSheetDataset,
)
from ingest.records import DisposalListSummary
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.models import QcIssue, Severity

RULE_ID = "disposal_semantic_review"

SYSTEM_PROMPT = """你是固定资产审计底稿中 K.02.2 处置测试的语义复核助手。
你只评价文字说明和证据描述是否充分，不重新计算金额，不重新匹配样本，也不推翻确定性规则结论。

硬性边界：
1. deterministic_rule_findings 是既定事实；不得将 FAIL/WARN 改为 PASS。
2. 不判断合同、发票、审批单、回款证明等外部证据真伪。
3. 信息不足时返回 unclear，不自行补充事实。
4. 只评价以下主题：
   - waiver_reason：不执行或受限执行理由是否具体，是否仅写低于 TE/TT、无异常等空泛表述。
   - sample_selection：关键项目、代表性样本和替换样本选择理由是否清楚。
   - evidence_description：出售/报废支持性证据描述是否足以识别具体证据及其用途。
   - exception_followup：规则发现的差异、属性否定结果是否有原因、追加程序和结论。
   - other_reduction_treatment：其他减少是否说明由何种程序处理，是否与出售/报废总体区分。

请只返回 JSON 对象，不返回 markdown。"""

USER_TEMPLATE = """请复核 K.02.2 处置测试语义充分性，返回：
{{
  "topics": [
    {{
      "topic": "waiver_reason|sample_selection|evidence_description|exception_followup|other_reduction_treatment",
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

_LABELS = {
    "waiver_reason": "\u4e0d\u6267\u884c\u7406\u7531",
    "sample_selection": "\u6837\u672c\u9009\u62e9\u4f9d\u636e",
    "evidence_description": "\u652f\u6301\u6027\u8bc1\u636e\u63cf\u8ff0",
    "exception_followup": "\u5f02\u5e38\u8ddf\u8fdb",
    "other_reduction_treatment": "\u5176\u4ed6\u51cf\u5c11\u5904\u7406",
}

_WAIVED_PATH_KINDS = {
    "summary_waived",
    "test_sheet_waiver_note",
    "documented_limited",
}

_EXECUTED_ONLY_TOPICS = {
    "sample_selection",
    "evidence_description",
    "exception_followup",
}



def build_disposal_review_payload(
    *,
    disposal_list_summary: DisposalListSummary | None = None,
    disposal_test: DisposalTestSheetDataset | None = None,
    disposal_sample_output: DisposalSampleOutputDataset | None = None,
    disposal_execution_path: DisposalExecutionPathDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
) -> dict[str, Any]:
    return {
        "disposal_list_summary": disposal_list_summary.to_dict() if disposal_list_summary else None,
        "disposal_execution_path": disposal_execution_path.to_dict() if disposal_execution_path else None,
        "disposal_test": _test_excerpt(disposal_test),
        "disposal_sample_output": _sample_excerpt(disposal_sample_output),
        "deterministic_rule_findings": [
            {
                "rule_id": issue.rule_id,
                "field": issue.field,
                "severity": issue.severity.value,
                "message": issue.message,
                "source_sheet": issue.source_sheet,
                "source_row": issue.source_row,
                "source_col": getattr(issue, "source_col", None),
            }
            for issue in (prior_issues or [])[:25]
        ],
        "review_policy": {
            "do_not_override_rule_findings": True,
            "do_not_calculate_amounts_or_match_samples": True,
            "semantic_sufficiency_only": True,
        },
    }


def build_disposal_llm_issues(
    config: LlmConfig,
    *,
    disposal_list_summary: DisposalListSummary | None = None,
    disposal_test: DisposalTestSheetDataset | None = None,
    disposal_sample_output: DisposalSampleOutputDataset | None = None,
    disposal_execution_path: DisposalExecutionPathDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
) -> list[QcIssue]:
    if not config.enabled:
        return []
    if (
        disposal_test is not None
        and disposal_test.module_assessments
        and disposal_test.usable_for_rules is False
    ):
        return []
    if (
        disposal_sample_output is not None
        and disposal_sample_output.module_assessments
        and disposal_sample_output.usable_for_rules is False
    ):
        return []
    payload = build_disposal_review_payload(
        disposal_list_summary=disposal_list_summary,
        disposal_test=disposal_test,
        disposal_sample_output=disposal_sample_output,
        disposal_execution_path=disposal_execution_path,
        prior_issues=prior_issues,
    )
    try:
        review = chat_completion_json(
            config,
            system=SYSTEM_PROMPT,
            user=USER_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False, indent=2)),
        )
    except LlmClientError:
        return []
    return _issues_from_review(review or {}, payload)


def _test_excerpt(test: DisposalTestSheetDataset | None) -> dict[str, Any] | None:
    if test is None:
        return None
    return {
        "source_sheet": test.source_sheet,
        "waiver_note_text": test.waiver_note_text,
        "tested_samples": [sample.to_dict() for sample in test.tested_samples[:20]],
        "module_assessments": [module.to_dict() for module in test.module_assessments],
        "usable_for_rules": test.usable_for_rules,
    }


def _sample_excerpt(output: DisposalSampleOutputDataset | None) -> dict[str, Any] | None:
    if output is None:
        return None
    return {
        "source_sheet": output.source_sheet,
        "parameters": {key: item.to_dict() for key, item in output.parameters.items()},
        "amounts": {key: item.to_dict() for key, item in output.amounts.items()},
        "selected_samples": [sample.to_dict() for sample in output.selected_samples[:20]],
        "module_assessments": [module.to_dict() for module in output.module_assessments],
        "usable_for_rules": output.usable_for_rules,
    }


def _issues_from_review(review: dict[str, Any], payload: dict[str, Any]) -> list[QcIssue]:
    topics = review.get("topics") if isinstance(review.get("topics"), list) else []
    issues: list[QcIssue] = []
    for item in topics:
        if not isinstance(item, dict):
            continue
        assessment = str(item.get("assessment", "")).strip().lower()
        if assessment == "sufficient":
            continue
        topic = str(item.get("topic", "disposal_semantic")).strip()
        path = payload.get("disposal_execution_path") or {}
        path_kind = path.get("path_kind") if isinstance(path, dict) else None
        if topic == "waiver_reason" and path_kind not in _WAIVED_PATH_KINDS:
            continue
        if topic in _EXECUTED_ONLY_TOPICS and path_kind in _WAIVED_PATH_KINDS:
            continue
        summary = payload.get("disposal_list_summary") or {}
        other_amount = summary.get("other_reduction_net_value") if isinstance(summary, dict) else None
        if topic == "other_reduction_treatment" and str(other_amount or "0").strip() in {
            "",
            "0",
            "0.0",
            "0.00",
        }:
            continue
        rationale = str(item.get("rationale", "")).strip()
        action = str(item.get("suggested_action", "")).strip()
        severity = Severity.WARN if assessment == "insufficient" else Severity.NEED_REVIEW
        message = (
            f"K.02.2 {_LABELS.get(topic, topic)}"
            f"{'\u8bf4\u660e\u4e0d\u8db3' if assessment == 'insufficient' else '\u9700\u4eba\u5de5\u590d\u6838'}"
        )
        if rationale:
            message += f"\uff1a{rationale}"
        source_sheet, source_row, source_col = _topic_anchor(topic, payload)
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=topic,
                severity=severity,
                message=message,
                suggestion=action or "\u8865\u5145\u5177\u4f53\u8bf4\u660e\uff0c\u5e76\u56de\u5e94\u786e\u5b9a\u6027\u89c4\u5219\u53d1\u73b0\u3002",
                procedure_code="K.02.2",
                source_sheet=source_sheet,
                source_row=source_row,
                source_col=source_col,
                review_source="LLM\u8f85\u52a9\u5224\u65ad",
                llm_review_type="K.02.2 \u5904\u7f6e\u6d4b\u8bd5\u8bed\u4e49\u590d\u6838",
            )
        )
    return issues


def _source_sheet(payload: dict[str, Any]) -> str:
    for key in ("disposal_test", "disposal_sample_output", "disposal_list_summary"):
        value = payload.get(key)
        if isinstance(value, dict) and value.get("source_sheet"):
            return str(value["source_sheet"])
    return "K.02.2"


def _source_row(payload: dict[str, Any]) -> int | None:
    test = payload.get("disposal_test")
    if isinstance(test, dict):
        samples = test.get("tested_samples")
        if isinstance(samples, list):
            for sample in samples:
                if isinstance(sample, dict) and isinstance(sample.get("source_row"), int):
                    return sample["source_row"]
    output = payload.get("disposal_sample_output")
    if isinstance(output, dict):
        selected = output.get("selected_samples")
        if isinstance(selected, list):
            for sample in selected:
                if isinstance(sample, dict) and isinstance(sample.get("source_row"), int):
                    return sample["source_row"]
    return None


def _topic_anchor(topic: str, payload: dict[str, Any]) -> tuple[str, int | None, int | None]:
    if topic == "other_reduction_treatment":
        summary = payload.get("disposal_list_summary")
        if isinstance(summary, dict):
            buckets = summary.get("buckets")
            if isinstance(buckets, list):
                for bucket in buckets:
                    if not isinstance(bucket, dict) or bucket.get("bucket_key") != "other":
                        continue
                    rows = bucket.get("source_rows")
                    if isinstance(rows, list):
                        for row in rows:
                            if isinstance(row, int):
                                return str(summary.get("source_sheet") or "\u5904\u7f6e\u6e05\u5355"), row, None
    if topic in _EXECUTED_ONLY_TOPICS:
        for hint in payload.get("deterministic_rule_findings") or []:
            if not isinstance(hint, dict):
                continue
            if hint.get("source_sheet") and isinstance(hint.get("source_row"), int):
                return (
                    str(hint.get("source_sheet")),
                    hint.get("source_row"),
                    hint.get("source_col") if isinstance(hint.get("source_col"), int) else None,
                )
    if topic == "waiver_reason":
        path = payload.get("disposal_execution_path")
        if isinstance(path, dict) and isinstance(path.get("summary_source_row"), int):
            return "\u6c47\u603b", path["summary_source_row"], None
        test = payload.get("disposal_test")
        if isinstance(test, dict) and test.get("waiver_note_text"):
            return str(test.get("source_sheet") or "K.02.2"), _source_row(payload), None
    return _source_sheet(payload), _source_row(payload), None
