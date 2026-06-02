from __future__ import annotations

import json

from ingest.lead_sheet import LeadSheetDataset
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.models import QcIssue, Severity

RULE_EXPECTATION = "lead_expectation_semantic"
RULE_FLUCTUATION = "lead_fluctuation_notes_semantic"

_EXPECTATION_SYSTEM = """你是固定资产审计 K.00 Lead 底稿复核助手。只判断“预期分析”是否充分。
判断时必须贴近固定资产 K1 底稿实际执行口径；引入 LLM 后仍需人工确认复核。

输出含义：
- sufficient：预期分析包含主要业务原因和变动方向，且与输入中后推明细表/引导表可见方向不冲突。
- insufficient：预期分析明显缺少业务原因，或变动方向与输入中后推明细表合计金额方向冲突。
- unclear：属于会计政策/会计估计变化或其他未覆盖情形，或输入不足以判断方向一致性。

不足表达：
1) 包含主要业务原因和变动方向，但变动方向与 K.01 后推明细表中合计金额变动方向不一致，例如预期原值存在新增，而后推明细表中购置及在建工程转入金额为 0；
2) 仅写“预计增加”“预计减少”“无异常”等结论，未说明业务原因。

可接受表达：
针对新增、减少、在建工程转入、折旧费用、转让、外汇和其他调整，只要包含主要业务原因和变动方向，且与输入可见的后推明细表合计金额变动方向一致，可以判断 sufficient；不要因为没有使用标准审计术语而判不足。

不确定表达：
1) 会计政策及会计估计类，如折旧方法、使用寿命，默认无重大变化；如果预期分析中存在变化，需要对应的合理原因说明，否则返回 unclear；
2) 输入未提供后推明细表方向或证据不足时，不得编造，返回 unclear；
3) 其他未涵盖情况。
只输出 JSON。"""

_FLUCTUATION_SYSTEM = """你是固定资产审计 K.00 Lead 底稿复核助手。只判断“异常波动说明”是否充分。
判断时必须贴近固定资产 K1 底稿实际执行口径；引入 LLM 后仍需人工确认复核。

逻辑判定：
1) Lead 引导表中变动超过阈值（波动幅度 CNY）时，必须添加 Note 进行分析，且 Note 编号应与下方波动分析编号一致；超过阈值但未添加索引编号，需要提示。
2) 未超过阈值时，可以选择性添加 Note；如存在“无金额变动超过 TT”“无变动大于 10%”等描述，判断条件可放宽。
3) 比较金额时注意单位换算，避免误判，例如 k=千，m=百万。

不足表达：
1) 波动说明中的变动金额与 Lead 引导表不一致；
2) 只描述变动金额和变动幅度，未描述变动原因；
3) 超过阈值但未见 Note 索引或下方对应波动分析。

可接受表达：
1) 若引导表变动超过阈值，异常波动说明中的金额与 Lead 引导表一致，且包含业务原因，并提到已检查的支持资料或对应程序，可以判断 sufficient。
2) 若引导表变动未超过阈值，存在“无金额变动超过 TT”“无变动大于 10%”之类描述，可放宽；若存在变动金额及业务说明，检查其是否相符及合理。

其他未涵盖情况返回 unclear；不得编造输入中没有的金额、Note 编号、支持资料或程序。
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
        "review_hint": (
            "如需判断预期方向与 K.01 后推明细表方向是否一致，只能使用输入中可见的 "
            "movement_rows/volatility 或其他摘录；证据不足时返回 unclear。"
        ),
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
            review_source="LLM辅助判断",
            llm_review_type="Lead预期分析充分性",
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
        "volatility": lead.volatility.to_dict() if lead.volatility else None,
        "review_hint": (
            "若 movement_rows 中存在超过阈值的变动，应关注 notes/索引编号与下方波动说明是否对应；"
            "比较金额时注意 k=千、m=百万等单位换算。"
        ),
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
            review_source="LLM辅助判断",
            llm_review_type="Lead异常波动说明充分性",
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
