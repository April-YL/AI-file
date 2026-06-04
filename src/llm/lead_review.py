from __future__ import annotations

import json
from typing import Any

from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.reconciliation import ReconciliationCheck
from ingest.rollforward_sheet import RollforwardSheetDataset
from ingest.summary_sheet import SummarySheetDataset
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.lead_common import exceeds_volatility_threshold
from rules.parsing import parse_amount
from rules.models import QcIssue, Severity

RULE_EXPECTATION = "lead_expectation_semantic"
RULE_FLUCTUATION = "lead_fluctuation_notes_semantic"

_EXPECTATION_SYSTEM = """你是固定资产审计 K.00 Lead 底稿复核助手。只判断“预期分析”是否充分。
判断时必须贴近固定资产 K1 底稿实际执行口径；引入 LLM 后仍需人工确认复核。

输出含义：
- sufficient：预期分析包含主要业务原因和变动方向，且与输入中后推明细表/引导表可见方向不冲突。
- insufficient：预期分析明显缺少业务原因，或变动方向与输入中后推明细表合计金额方向冲突。
- unclear：属于会计政策/会计估计变化或其他未覆盖情形，或输入不足以判断方向一致性；unclear 仅作内部判断，不应要求底稿编制者补充 K.01 期初、期末及变动金额。

不足表达：
1) 包含主要业务原因和变动方向，但变动方向与 K.01 后推明细表中合计金额变动方向不一致，例如预期原值存在新增，而后推明细表中购置及在建工程转入金额为 0；
2) 仅写“预计增加”“预计减少”“无异常”等结论，未说明业务原因。

可接受表达：
针对新增、减少、在建工程转入、折旧费用、转让、外汇和其他调整，只要包含主要业务原因和变动方向，且与输入可见的后推明细表合计金额变动方向一致，可以判断 sufficient；不要因为没有使用标准审计术语而判不足。
标准 K.00 Lead 预期分析不要求单独对“减值准备”科目逐行建立预期；不得仅因未写“减值准备预期分析”而判 insufficient。减值相关事项应在减值测试/减值迹象识别程序或异常波动说明充分性中关注。
如果预期分析已包含主要业务原因和变动方向，且输入没有显示与 Lead/K.01 可见方向冲突，应判断 sufficient；不得仅因想进一步验证 K.01 期初、期末或变动金额而返回 insufficient。

不确定表达：
1) 会计政策及会计估计类，如折旧方法、使用寿命，默认无重大变化；如果预期分析中存在变化，需要对应的合理原因说明，否则返回 unclear；
2) 输入未提供后推明细表方向、汇总页 PSP 状态、清单金额或其他证据不足时，不得编造，返回 unclear；
3) 其他未涵盖情况。
只输出 JSON。"""

_FLUCTUATION_SYSTEM = """你是固定资产审计 K.00 Lead 底稿复核助手。只判断“异常波动说明”是否充分。
判断时必须贴近固定资产 K1 底稿实际执行口径；引入 LLM 后仍需人工确认复核。

逻辑判定：
1) 只对输入 movement_rows 中 note_required_by_threshold=true 的行执行强制 Note 判断。
2) 当金额阈值和比例阈值同时存在时，必须“金额变动超过阈值”且“比例变动超过阈值”才需要 Note；金额变动为 0 的行，即使比例显示 100%，也不得仅因比例判为不足。
3) note_required_by_threshold=false 但已有 Note 的行，属于底稿编制者自愿补充分析；可以检查是否明显自相矛盾，但不得按“异常波动必须覆盖”标准报不足。
4) 比较金额时注意单位换算，避免误判，例如 k=千，m=百万。

不足表达：
1) 波动说明中的变动金额与 Lead 引导表不一致；
2) 只描述变动金额和变动幅度，未描述变动原因；
3) 超过阈值但未见 Note 索引或下方对应波动分析。

可接受表达：
1) 若引导表变动超过阈值，异常波动说明中的金额与 Lead 引导表一致，且包含业务原因，并提到已检查的支持资料或对应程序，可以判断 sufficient。
2) 若引导表变动未超过阈值，存在“无金额变动超过 TT”“无变动大于 10%”之类描述，可放宽；若存在变动金额及业务说明，检查其是否相符及合理。

其他未涵盖情况返回 unclear；不得编造输入中没有的金额、Note 编号、支持资料、程序页或汇总页执行状态。
只输出 JSON。"""


def build_lead_semantic_issues(
    lead: LeadSheetDataset,
    config: LlmConfig,
    *,
    semantic_context: dict[str, Any] | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    issues.extend(_review_expectation_semantic(lead, config, semantic_context=semantic_context))
    issues.extend(_review_fluctuation_notes_semantic(lead, config, semantic_context=semantic_context))
    return issues


def build_lead_semantic_context(
    *,
    summary: SummarySheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
    addition_list: FaListDataset | None = None,
    disposal_list: FaListDataset | None = None,
    reconciliations: list[ReconciliationCheck] | None = None,
    workbook_sheet_titles: list[str] | None = None,
) -> dict[str, Any]:
    """构造 Lead 语义复核的整本底稿上下文。"""
    context: dict[str, Any] = {}
    if summary is not None:
        context["summary_psp"] = _summary_context(summary)
    if rollforward is not None:
        context["k01_rollforward"] = _rollforward_context(rollforward)
    if addition_list is not None:
        context["addition_list"] = _asset_list_context(addition_list)
    if disposal_list is not None:
        context["disposal_list"] = _asset_list_context(disposal_list)
    if reconciliations:
        context["reconciliations"] = [c.to_dict() for c in reconciliations[:8]]
    if workbook_sheet_titles:
        context["workbook_sheets"] = workbook_sheet_titles[:80]
    return context


def _review_expectation_semantic(
    lead: LeadSheetDataset,
    config: LlmConfig,
    *,
    semantic_context: dict[str, Any] | None = None,
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
            "判断预期方向与 K.01 后推明细表、汇总页 PSP、清单或勾稽结果是否一致时，"
            "只能使用输入中可见的 movement_rows/volatility/workbook_context；证据不足时返回 unclear。"
        ),
        "workbook_context": _compact_lead_semantic_context(
            semantic_context or {},
            lead=lead,
            purpose="expectation",
        ),
    }
    out = _call_semantic_review(
        config=config,
        system=_EXPECTATION_SYSTEM,
        payload=payload,
        rationale_hint="预期分析",
    )
    if out is None or out["assessment"] in {"sufficient", "unclear"}:
        return []
    sev = Severity.WARN
    msg = "Lead 预期分析语义上不足"
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
    *,
    semantic_context: dict[str, Any] | None = None,
) -> list[QcIssue]:
    notes = (lead.fluctuation_notes or "").strip()
    # 空值由确定性规则 unexpected_movement_investigation 处理；这里仅评估“已填写但是否充分”。
    if not notes:
        return []
    payload = {
        "source_sheet": lead.source_sheet,
        "fluctuation_notes": notes,
        "movement_rows": _movement_rows_for_fluctuation_review(lead),
        "volatility": lead.volatility.to_dict() if lead.volatility else None,
        "review_hint": (
            "只有 note_required_by_threshold=true 的行才必须有 notes/索引编号并与下方波动说明对应；"
            "note_required_by_threshold=false 但已有 notes 的行属于自愿说明，不按强制异常波动标准判断。"
            "并结合 workbook_context 中的 K.01、清单、汇总页 PSP 和勾稽结果判断说明是否有支持。"
            "比较金额时注意 k=千、m=百万等单位换算。"
        ),
        "workbook_context": _compact_lead_semantic_context(
            semantic_context or {},
            lead=lead,
            purpose="fluctuation",
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


def _parse_percent(value: str | None):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    pct = parse_amount(text.rstrip("%"))
    if pct is None:
        return None
    if text.endswith("%"):
        return pct / 100
    return pct


def _movement_rows_for_fluctuation_review(lead: LeadSheetDataset) -> list[dict[str, Any]]:
    vol_amount = parse_amount(lead.volatility.amount) if lead.volatility else None
    vol_percent = _parse_percent(lead.volatility.percent) if lead.volatility else None
    rows: list[dict[str, Any]] = []
    for r in lead.movement_rows[:12]:
        movement_amt = parse_amount(r.values.get("movement_amount") or r.values.get("movement"))
        movement_pct = _parse_percent(r.values.get("movement_pct"))
        required = exceeds_volatility_threshold(
            movement_amt,
            movement_pct,
            vol_amount=vol_amount,
            vol_percent=vol_percent,
        )
        notes = r.values.get("notes")
        rows.append(
            {
                "account_label": r.account_label,
                "source_row": r.source_row,
                "movement": r.values.get("movement"),
                "movement_amount": r.values.get("movement_amount"),
                "movement_pct": r.values.get("movement_pct"),
                "notes": notes,
                "note_required_by_threshold": required,
                "volatility_threshold_reason": _threshold_reason(
                    movement_amt=movement_amt,
                    movement_pct=movement_pct,
                    vol_amount=vol_amount,
                    vol_percent=vol_percent,
                    required=required,
                    has_note=bool(str(notes or "").strip()),
                ),
            }
        )
    return rows


def _threshold_reason(
    *,
    movement_amt,
    movement_pct,
    vol_amount,
    vol_percent,
    required: bool,
    has_note: bool,
) -> str:
    if movement_amt is not None and movement_amt == 0:
        return "金额变动为0；即使比例显示100%，也不属于强制异常波动说明。"
    if vol_amount is not None and vol_percent is not None:
        return (
            "金额和比例均超过阈值，必须有Note。"
            if required
            else "金额阈值和比例阈值需同时超过；本行未同时超过。"
        )
    if required:
        return "可取得的阈值已超过，必须有Note。"
    if has_note:
        return "未超过强制阈值但底稿已有自愿Note；仅检查是否明显自相矛盾。"
    return "未超过强制阈值。"


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


def _compact_lead_semantic_context(
    context: dict[str, Any],
    *,
    lead: LeadSheetDataset,
    purpose: str,
) -> dict[str, Any]:
    """保留 Lead 判断依据，裁掉与本质检点无关的大块样本数据。"""
    if not context:
        return {}
    out: dict[str, Any] = {}
    summary = context.get("summary_psp")
    if isinstance(summary, dict):
        out["summary_psp"] = _compact_summary_context(summary)
    rollforward = context.get("k01_rollforward")
    if isinstance(rollforward, dict):
        out["k01_rollforward"] = _compact_rollforward_context(rollforward)
    reconciliations = context.get("reconciliations")
    if isinstance(reconciliations, list) and reconciliations:
        out["reconciliations"] = reconciliations[:6]

    need_addition = _lead_text_contains(lead, ("新增", "购置", "addition", "purchase"))
    need_disposal = _lead_text_contains(lead, ("处置", "减少", "disposal", "retirement"))
    if purpose == "fluctuation":
        # 波动说明经常会引用新增/处置清单作为支持证据；仅保留汇总级信息。
        need_addition = need_addition or bool(context.get("addition_list"))
        need_disposal = need_disposal or bool(context.get("disposal_list"))
    if need_addition and isinstance(context.get("addition_list"), dict):
        out["addition_list"] = _compact_asset_list_context(context["addition_list"])
    if need_disposal and isinstance(context.get("disposal_list"), dict):
        out["disposal_list"] = _compact_asset_list_context(context["disposal_list"])
    return out


def _lead_text_contains(lead: LeadSheetDataset, tokens: tuple[str, ...]) -> bool:
    text_parts: list[str] = [lead.fluctuation_notes or ""]
    text_parts.extend(str(e.account_change or "") for e in lead.expectations)
    text_parts.extend(str(e.expectation or "") for e in lead.expectations)
    text_parts.extend(str(r.account_label or "") for r in lead.movement_rows)
    blob = " ".join(text_parts).lower()
    return any(token.lower() in blob for token in tokens)


def _compact_summary_context(summary: dict[str, Any]) -> dict[str, Any]:
    programs = summary.get("programs") if isinstance(summary.get("programs"), list) else []
    focused = []
    for row in programs:
        if not isinstance(row, dict):
            continue
        status = str(row.get("execution_status") or "").strip()
        waiver = str(row.get("waiver_reason") or "").strip()
        if status or waiver:
            focused.append(
                {
                    "procedure_name": row.get("procedure_name"),
                    "sheet_ref": row.get("sheet_ref"),
                    "execution_status": row.get("execution_status"),
                    "waiver_reason": row.get("waiver_reason"),
                    "source_row": row.get("source_row"),
                    "is_psp": row.get("is_psp"),
                }
            )
        if len(focused) >= 12:
            break
    return {
        "source_sheet": summary.get("source_sheet"),
        "programs": focused,
    }


def _compact_rollforward_context(rollforward: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_sheet": rollforward.get("source_sheet"),
        "has_movement_rows": rollforward.get("has_movement_rows"),
        "opening_totals": rollforward.get("opening_totals"),
        "ending_totals": rollforward.get("ending_totals"),
        "section_presence": rollforward.get("section_presence"),
        "tb_reconciliation_detected": rollforward.get("tb_reconciliation_detected"),
        "tb_difference_values": rollforward.get("tb_difference_values"),
        "table3_check_values": rollforward.get("table3_check_values"),
        "table4_difference": rollforward.get("table4_difference"),
        "notes": (rollforward.get("notes") or [])[:6],
        "tb_notes_text": _truncate_text(rollforward.get("tb_notes_text"), 800),
        "table3_notes_text": _truncate_text(rollforward.get("table3_notes_text"), 800),
        "table4_notes_text": _truncate_text(rollforward.get("table4_notes_text"), 800),
    }


def _compact_asset_list_context(asset_list: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_sheet": asset_list.get("source_sheet"),
        "record_count": asset_list.get("record_count"),
        "mapped_fields": asset_list.get("mapped_fields"),
        "totals": asset_list.get("totals"),
    }


def _truncate_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _summary_context(summary: SummarySheetDataset) -> dict[str, Any]:
    return {
        "source_sheet": summary.source_sheet,
        "programs": [
            {
                "procedure_name": p.procedure_name,
                "sheet_ref": p.sheet_ref,
                "execution_status": p.execution_status,
                "waiver_reason": p.waiver_reason,
                "notes": p.notes,
                "source_row": p.source_row,
                "is_psp": p.is_psp,
            }
            for p in summary.programs[:20]
        ],
        "notes": summary.notes[:8],
    }


def _rollforward_context(rollforward: RollforwardSheetDataset) -> dict[str, Any]:
    return {
        "source_sheet": rollforward.source_sheet,
        "has_movement_rows": rollforward.has_movement_rows,
        "opening_totals": _value_dict(rollforward.opening_totals),
        "ending_totals": _value_dict(rollforward.ending_totals),
        "section_presence": rollforward.section_presence,
        "section_evidence": rollforward.section_evidence,
        "tb_reconciliation_detected": rollforward.tb_reconciliation_detected,
        "tb_difference_values": [str(v) for v in rollforward.tb_difference_values[:8]],
        "tb_notes_text": rollforward.tb_notes_text,
        "table3_check_values": [str(v) for v in rollforward.table3_check_values[:8]],
        "table3_notes_text": rollforward.table3_notes_text,
        "table4_difference": (
            str(rollforward.table4_difference)
            if rollforward.table4_difference is not None
            else None
        ),
        "table4_notes_text": rollforward.table4_notes_text,
        "notes": rollforward.notes[:12],
    }


def _asset_list_context(dataset: FaListDataset) -> dict[str, Any]:
    return {
        "source_sheet": dataset.source_sheet,
        "record_count": len(dataset.records),
        "mapped_fields": [m.standard_field for m in dataset.mapped_fields],
        "totals": {
            field: total
            for field in (
                "original_value",
                "accumulated_depreciation",
                "impairment_provision",
                "net_value",
            )
            if (total := _record_total(dataset, field)) is not None
        },
        "sample_rows": [
            {
                "source_row": r.source_row,
                "asset_id": r.asset_id,
                "asset_name": r.asset_name,
                "original_value": r.original_value,
                "accumulated_depreciation": r.accumulated_depreciation,
                "net_value": r.net_value,
            }
            for r in dataset.records[:5]
        ],
    }


def _record_total(dataset: FaListDataset, field: str) -> str | None:
    total = None
    for rec in dataset.records:
        val = parse_amount(getattr(rec, field, None))
        if val is None:
            continue
        total = val if total is None else total + val
    return str(total) if total is not None else None


def _value_dict(values: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in values.items() if v is not None}
