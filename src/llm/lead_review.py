from __future__ import annotations

import json

from ingest.lead_sheet import LeadSheetDataset
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.models import QcIssue, Severity

RULE_EXPECTATION = "lead_expectation_semantic"
RULE_FLUCTUATION = "lead_fluctuation_notes_semantic"

_EXPECTATION_SYSTEM = """你是固定资产审计 Lead 底稿复核助手。只判断“预期分析”是否充分。
判断标准：
1) 是否说明主要变动驱动（新增/处置/折旧/减值等）；
2) 是否体现金额或比例阈值口径（TE/TT/SAD 或同等口径）；
3) 是否具备可复核性（至少说明依据或证据来源）；
4) 不确定时返回 unclear，不得编造。
只输出 JSON。"""

_FLUCTUATION_SYSTEM = """你是固定资产审计 Lead 底稿复核助手。只判断“异常波动说明”是否充分。
判断标准：
1) 是否解释异常波动原因及业务背景；
2) 是否说明影响与风险（至少提及错报/波动风险或后续程序）；
3) 是否给出支持性证据或后续跟进动作；
4) 不确定时返回 unclear，不得编造。
只输出 JSON。"""


def build_lead_semantic_issues(
    lead: LeadSheetDataset,
    config: LlmConfig,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    issues.extend(_review_expectation_semantic(lead, config))
    issues.extend(_review_fluctuation_notes_semantic(lead, config))
    return issues


def _review_expectation_semantic(
    lead: LeadSheetDataset,
    config: LlmConfig,
) -> list[QcIssue]:
    # 无预期行时由确定性规则 lead_expectation_analysis 处理，不在此重复报错。
    if not lead.expectations:
        return []
    rows = [
        {
            "account_change": r.account_change,
            "expectation": r.expectation,
            "source_row": r.source_row,
        }
        for r in lead.expectations[:10]
    ]
    payload = {
        "source_sheet": lead.source_sheet,
        "expectation_rows": rows,
        "volatility": lead.volatility.to_dict() if lead.volatility else None,
    }
    out = _call_semantic_review(
        config=config,
        system=_EXPECTATION_SYSTEM,
        payload=payload,
        rationale_hint="预期分析",
    )
    if out is None or out["assessment"] == "sufficient":
        return []
    sev = Severity.WARN if out["assessment"] == "insufficient" else Severity.NEED_REVIEW
    msg = "Lead 预期分析语义上不足" if out["assessment"] == "insufficient" else "Lead 预期分析语义不明确"
    if out["rationale"]:
        msg += f"；模型提示：{out['rationale']}"
    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_EXPECTATION,
            field="expectation_semantic",
            severity=sev,
            message=msg,
            suggestion=out["suggestion"] or "补充主要变动驱动、阈值口径和证据来源说明。",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
        )
    ]


def _review_fluctuation_notes_semantic(
    lead: LeadSheetDataset,
    config: LlmConfig,
) -> list[QcIssue]:
    notes = (lead.fluctuation_notes or "").strip()
    # 空值由确定性规则 unexpected_movement_investigation 处理；这里仅评估“已填写但是否充分”。
    if not notes:
        return []
    payload = {
        "source_sheet": lead.source_sheet,
        "fluctuation_notes": notes,
        "movement_rows": [
            {
                "account_label": r.account_label,
                "source_row": r.source_row,
                "movement": r.values.get("movement"),
                "movement_pct": r.values.get("movement_pct"),
                "notes": r.values.get("notes"),
            }
            for r in lead.movement_rows[:12]
        ],
    }
    out = _call_semantic_review(
        config=config,
        system=_FLUCTUATION_SYSTEM,
        payload=payload,
        rationale_hint="异常波动说明",
    )
    if out is None or out["assessment"] == "sufficient":
        return []
    sev = Severity.WARN if out["assessment"] == "insufficient" else Severity.NEED_REVIEW
    msg = "Lead 异常波动说明语义上不足" if out["assessment"] == "insufficient" else "Lead 异常波动说明语义不明确"
    if out["rationale"]:
        msg += f"；模型提示：{out['rationale']}"
    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_FLUCTUATION,
            field="fluctuation_notes_semantic",
            severity=sev,
            message=msg,
            suggestion=out["suggestion"] or "补充异常原因、风险影响及支持证据或后续程序。",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
        )
    ]


def _call_semantic_review(
    *,
    config: LlmConfig,
    system: str,
    payload: dict,
    rationale_hint: str,
) -> dict[str, str] | None:
    user = (
        f"请判断该{rationale_hint}是否充分。返回 JSON：\n"
        '{ "assessment":"sufficient|insufficient|unclear", "rationale":"", "suggested_action":"" }\n'
        f"输入：{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        out = chat_completion_json(config, system=system, user=user)
    except LlmClientError:
        return None
    assessment = str(out.get("assessment", "")).strip().lower()
    if assessment not in {"sufficient", "insufficient", "unclear"}:
        return None
    return {
        "assessment": assessment,
        "rationale": str(out.get("rationale", "")).strip(),
        "suggestion": str(out.get("suggested_action", "")).strip(),
    }
