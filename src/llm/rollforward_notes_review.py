"""K.01 后推表 — 材料差异 Notes 语义复核（TB / 表3 / 表4 分专题）。"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount

RULE_ID = "rollforward_notes_semantic"
_AMOUNT_TOL = Decimal("0.01")

_SYSTEM = """你是固定资产审计 K.01 后推表「差异调查 Notes」复核助手。
仅判断已有 Notes 是否充分回应**该专题**的材料差异；不得编造金额、程序页、证据或外部系统数据。

SOP K1.01【02】⑤：超过 SAD 的差异应调查并记录。充分的 Notes 通常应覆盖（不必逐字四个标题）：
1) 差异原因（口径/取数/重分类/分类差异等）
2) 调查过程（核对对象、步骤或证据/程序索引）
3) 处理结论（是否接受、是否需要调整）
4) 是否需进一步审计程序（如索引 K.02/K.03 或说明无需）

专题隔离（必须遵守）：
- tb_check：仅依据 TB/试算表核对摘录与 tb_notes_text；不得用表4折旧 Notes 代替 TB 差异说明
- table3_check：仅依据表3 check 摘录与 table3_notes_text；不得用 TB 或表4 Notes 代替表3 差异说明
- table4_depreciation：仅依据表4差异摘录与 table4_notes_text

必须判 insufficient 的典型情形：
1) 仅写“差异小于 SAD”“未超过 SAD”“无重大影响”等，但输入显示该专题差异金额已超过 SAD
2) 仅写“已核对”“无差异”“无异常”等空泛结论，未说明与本专题差异金额的关系
3) 仅写 NB/Note 编号但摘录中看不出该编号如何解释本专题差异
4) 将另一专题（如折旧费用）的原因用来解释 TB 或表3 差异，且未说明与本专题差异的对应关系

可判 sufficient：原因、过程、结论与摘录金额/口径一致，且与 Lead TE/SAD 门槛不冲突。
证据不足或跨专题混用无法判断时返回 unclear。

不得将 insufficient 改为 PASS；不得单独撤销确定性 FAIL（无 Notes、错专题 Notes）。

只输出 JSON，不要 markdown。"""

_USER_TEMPLATE = """请逐专题判断 Notes 恰当性。返回 JSON：
{{
  "topics": [
    {{
      "topic_id": "tb_check|table3_check|table4_depreciation",
      "assessment": "sufficient|insufficient|unclear",
      "rationale": "",
      "suggested_action": ""
    }}
  ]
}}

输入：
{payload}
"""


def should_review_rollforward_notes(
    rollforward: RollforwardSheetDataset | None,
    *,
    lead: LeadSheetDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
) -> bool:
    """是否存在需要 LLM 语义复核的 K.01 Notes 专题。"""
    if rollforward is None or not rollforward.source_sheet:
        return False
    if _build_review_topics(rollforward, lead=lead, prior_issues=prior_issues or []):
        return True
    return False


def build_rollforward_notes_review_payload(
    rollforward: RollforwardSheetDataset,
    *,
    lead: LeadSheetDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sad = _sad_from_lead(lead)
    return {
        "source_sheet": rollforward.source_sheet,
        "sad": str(sad) if sad is not None else None,
        "te": field_values(lead).get("te") if lead else None,
        "review_topics": _build_review_topics(
            rollforward,
            lead=lead,
            prior_issues=prior_issues or [],
        ),
        "deterministic_hints": _deterministic_hints(prior_issues or []),
        "workbook_context": workbook_context or {},
        "notes_policy": (
            "每个 topic 只使用对应 notes_text；"
            "tb_check 不得引用 table4_notes_text 作为 TB 差异说明。"
        ),
    }


def build_rollforward_notes_issues(
    rollforward: RollforwardSheetDataset | None,
    config: LlmConfig,
    *,
    lead: LeadSheetDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> list[QcIssue]:
    issues, _ = run_rollforward_notes_llm_review(
        rollforward,
        config,
        lead=lead,
        prior_issues=prior_issues,
        workbook_context=workbook_context,
    )
    return issues


def run_rollforward_notes_llm_review(
    rollforward: RollforwardSheetDataset | None,
    config: LlmConfig,
    *,
    lead: LeadSheetDataset | None = None,
    prior_issues: list[QcIssue] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> tuple[list[QcIssue], dict[str, Any] | None]:
    if not config.enabled or rollforward is None:
        return [], None
    topics = _build_review_topics(
        rollforward,
        lead=lead,
        prior_issues=prior_issues or [],
    )
    if not topics:
        return [], None

    payload = build_rollforward_notes_review_payload(
        rollforward,
        lead=lead,
        prior_issues=prior_issues,
        workbook_context=workbook_context,
    )
    user = _USER_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False, indent=2))
    try:
        review = chat_completion_json(config, system=_SYSTEM, user=user)
    except LlmClientError:
        return [], None
    if not review:
        return [], None
    return _issues_from_review(rollforward, review, topics), review


def _issues_from_review(
    rollforward: RollforwardSheetDataset,
    review: dict[str, Any],
    expected_topics: list[dict[str, Any]],
) -> list[QcIssue]:
    by_id = {t["topic_id"]: t for t in expected_topics}
    raw_topics = review.get("topics") if isinstance(review.get("topics"), list) else []
    issues: list[QcIssue] = []

    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        topic_id = str(item.get("topic_id", "")).strip()
        ctx = by_id.get(topic_id)
        if not ctx:
            continue
        assessment = str(item.get("assessment", "")).strip().lower()
        if assessment == "sufficient":
            continue
        rationale = str(item.get("rationale", "")).strip()
        action = str(item.get("suggested_action", "")).strip()
        label = str(ctx.get("label", topic_id))

        if assessment == "insufficient":
            sev = Severity.WARN
            msg = f"K.01 {label}：Notes 语义上不足"
        else:
            sev = Severity.NEED_REVIEW
            msg = f"K.01 {label}：Notes 需人工复核（语义不明确或专题混用）"

        if rationale:
            msg += f"；{rationale}"

        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=f"{topic_id}_notes_semantic",
                severity=sev,
                message=msg,
                suggestion=action
                or "补充差异原因、调查过程、处理结论，并说明是否需要进一步程序；确保 Notes 写在对应专题区域。",
                procedure_code="K.01",
                source_sheet=rollforward.source_sheet,
                source_row=ctx.get("source_row"),
                review_source="LLM辅助判断",
                llm_review_type=f"K.01差异Notes恰当性({label})",
            )
        )
    return issues


def _build_review_topics(
    rollforward: RollforwardSheetDataset,
    *,
    lead: LeadSheetDataset | None,
    prior_issues: list[QcIssue],
) -> list[dict[str, Any]]:
    sad = _sad_from_lead(lead)
    topics: list[dict[str, Any]] = []

    if sad is not None and rollforward.tb_reconciliation_detected:
        material = [d for d in rollforward.tb_difference_values if abs(d) > sad]
        if material and rollforward.tb_notes_text_present:
            topics.append(
                {
                    "topic_id": "tb_check",
                    "label": "TB/试算表核对",
                    "material_differences": [str(v) for v in material[:8]],
                    "difference_details": rollforward.tb_difference_details[:8],
                    "notes_text": rollforward.tb_notes_text,
                    "notes_row": rollforward.tb_notes_row,
                    "source_row": rollforward.tb_notes_row or rollforward.tb_difference_row,
                    "sad": str(sad),
                    "deterministic_rule": _hint_for_topic(prior_issues, "tb"),
                }
            )

    if sad is not None and rollforward.table3_check_values:
        material = [v for v in rollforward.table3_check_values if abs(v) > sad]
        if (
            material
            and rollforward.table3_notes_text_present
            and not _has_prior_notes_issue(prior_issues, "table3_notes_text")
        ):
            topics.append(
                {
                    "topic_id": "table3_check",
                    "label": "表3 check with 表1",
                    "material_differences": [str(v) for v in material[:8]],
                    "notes_text": rollforward.table3_notes_text,
                    "notes_row": rollforward.table3_notes_row,
                    "source_row": rollforward.table3_notes_row or rollforward.table3_check_row,
                    "sad": str(sad),
                    "deterministic_rule": _hint_for_topic(prior_issues, "table3"),
                }
            )

    if sad is not None and rollforward.table4_difference is not None:
        if (
            abs(rollforward.table4_difference) > sad
            and rollforward.table4_notes_text_present
            and not _has_prior_notes_issue(prior_issues, "table4_notes_text")
        ):
            topics.append(
                {
                    "topic_id": "table4_depreciation",
                    "label": "表4折旧与利润表核对",
                    "difference": str(rollforward.table4_difference),
                    "table4_pl_total": (
                        str(rollforward.table4_pl_total)
                        if rollforward.table4_pl_total is not None
                        else None
                    ),
                    "table4_rollforward_depreciation": (
                        str(rollforward.table4_rollforward_depreciation)
                        if rollforward.table4_rollforward_depreciation is not None
                        else None
                    ),
                    "notes_text": rollforward.table4_notes_text,
                    "notes_row": rollforward.table4_notes_row,
                    "source_row": rollforward.table4_notes_row or rollforward.table4_difference_row,
                    "sad": str(sad),
                    "deterministic_rule": _hint_for_topic(prior_issues, "table4"),
                }
            )

    return topics


def _deterministic_hints(issues: list[QcIssue]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for issue in issues:
        if issue.field and "notes" in issue.field:
            hints.append(
                {
                    "rule_id": issue.rule_id,
                    "field": issue.field,
                    "severity": issue.severity.value,
                    "message": issue.message,
                }
            )
    return hints[:12]


def _hint_for_topic(issues: list[QcIssue], token: str) -> str | None:
    for issue in issues:
        field = issue.field or ""
        if token in field or token in (issue.message or ""):
            return f"{issue.rule_id}:{issue.severity.value}"
    return None


def _has_prior_notes_issue(issues: list[QcIssue], field_name: str) -> bool:
    return any(
        issue.severity != Severity.PASS and issue.field == field_name
        for issue in issues
    )


def _sad_from_lead(lead: LeadSheetDataset | None) -> Decimal | None:
    if lead is None:
        return None
    sad = parse_amount(field_values(lead).get("sad"))
    if sad is None or sad <= 0:
        return None
    return sad
