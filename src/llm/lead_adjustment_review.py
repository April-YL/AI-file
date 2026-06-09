"""K.00 Lead 调整汇总表 — LLM 版式识别、行抽取与 MT-003 语义复核。"""

from __future__ import annotations

import json
import os
from typing import Any

from ingest.lead_adjustment_grid import load_adjustment_grid_for_lead
from ingest.lead_sheet import LeadSheetDataset
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.lead_adjustment_gating import PPE_DIRECT_ACCOUNT_ALIASES
from rules.lead_common import parse_threshold_amount
from rules.models import QcIssue, Severity

RULE_LAYOUT = "lead_adjustment_layout_review"
RULE_SEMANTIC = "lead_adjustment_semantic"

_SYSTEM_COMBINED = """你是固定资产审计 K.00 Lead「调整汇总表」复核助手。
输入含 adjustment_grid（块内原文）、guidance_adjustments（引导主表 PPE 行摘录）、ingest 弱解析行。
你必须遵守：
1. 不得编造编号、科目、金额、索引、程序页；证据不足标 unclear。
2. 先识别版式 amount_layout（single_signed_column / debit_credit_two_columns / unknown）
   与 sign_convention；unknown 时不得假设借正贷负。
3. 行级输出 signed_amount 与 amount_basis；双列时 debit-credit 合成（按 sign_convention）。
4. ppe_impact：direct=科目属于 PPE 原值/累计折旧/减值/净值；indirect=其他科目但影响 PPE；unclear=无法判断。
5. direct 行：与 guidance 同科目、同映射列（审计类→audit_adjustment，账表类→book_adjustment）比 signed_amount；
   允许仅符号相反且绝对值一致（match_reason 说明）。
6. indirect 行：不要求与 PPE 行金额相等；检查原因、计算过程、Refer 是否闭环（SOP【04】易错：其他科目调整仅索引）。
7. cross_account_policy=flag_not_fail：跨科目不得单独判金额 FAIL 语义；用 cross_account_flags 列出。
8. 声明无调整但存在非零 signed_amount → assessment=insufficient。
只输出一个 JSON 对象，不要 markdown。"""

_USER_COMBINED_TEMPLATE = """请完成调整汇总表复核，返回 JSON：
{{
  "layout": {{
    "amount_layout": "single_signed_column|debit_credit_two_columns|unknown",
    "sign_convention": "debit_positive_credit_negative|credit_positive_debit_negative|absolute_only|unknown",
    "confidence": "high|medium|low",
    "layout_notes": ""
  }},
  "rows": [
    {{
      "source_row": 0,
      "adjustment_category": "",
      "adjustment_ref": null,
      "account_label": "",
      "signed_amount": null,
      "amount_basis": "",
      "ppe_impact": "direct|indirect|unclear",
      "linked_ppe_accounts": [],
      "evidence_refs": [],
      "description": "",
      "confidence": "high|medium|low"
    }}
  ],
  "assessment": "sufficient|insufficient|unclear",
  "direct_amount_checks": [],
  "cross_account_flags": [],
  "rationale": "",
  "suggested_action": ""
}}

输入：
{payload}
"""


def should_review_adjustments(lead: LeadSheetDataset) -> bool:
    """是否应对该 Lead 调用调整汇总 LLM 复核。"""
    from ingest.lead_sheet_blocks import LeadBlockKind

    if lead.block(LeadBlockKind.ADJUSTMENT_SUMMARY) is None:
        return False
    if lead.adjustment_rows:
        return True
    for row in lead.movement_rows:
        for role in ("book_adjustment", "audit_adjustment"):
            amt = parse_threshold_amount(row.values.get(role))
            if amt is not None and amt != 0:
                return True
    return False


def build_guidance_adjustments(lead: LeadSheetDataset) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in lead.movement_rows:
        out.append(
            {
                "account_label": row.account_label,
                "source_row": row.source_row,
                "book_adjustment": row.values.get("book_adjustment"),
                "audit_adjustment": row.values.get("audit_adjustment"),
                "sheet_ref": row.sheet_ref,
            }
        )
    return out


def build_adjustment_review_payload(
    lead: LeadSheetDataset,
    *,
    adjustment_grid: dict[str, Any] | None = None,
    deterministic_hints: list[dict[str, Any]] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from ingest.lead_sheet_blocks import LeadBlockKind

    block = lead.block(LeadBlockKind.ADJUSTMENT_SUMMARY)
    payload: dict[str, Any] = {
        "source_sheet": lead.source_sheet,
        "adjustment_block": (
            {
                "anchor_row": block.anchor_row,
                "start_row": block.start_row,
                "end_row": block.end_row,
                "anchor_text": block.anchor_text,
                "confidence": block.confidence,
            }
            if block
            else None
        ),
        "adjustment_grid": (adjustment_grid or {}).get("grid"),
        "ingest_adjustment_rows": [r.to_dict() for r in lead.adjustment_rows[:25]],
        "guidance_adjustments": build_guidance_adjustments(lead),
        "guidance_sign_hint": (
            "引导表：管理层账表调整→book_adjustment；已更正/未更正审计调整→audit_adjustment；"
            "比对时使用 signed_amount，注意借贷方向可能与单列符号相反。"
        ),
        "ppe_direct_aliases": list(PPE_DIRECT_ACCOUNT_ALIASES),
        "deterministic_hints": deterministic_hints or [],
        "cross_account_policy": "flag_not_fail",
        "workbook_context": workbook_context or {},
    }
    return payload


def _llm_passes() -> int:
    raw = os.getenv("FA_QC_LLM_ADJUSTMENT_PASSES", "1").strip()
    try:
        n = int(raw)
    except ValueError:
        return 1
    return n if n in (1, 3) else 1


_LEAD017_ADDITIONAL_SYSTEM = """
Additional LEAD-017 instructions:
1. Do not compare the whole journal-entry net total with Lead guidance adjustments.
   A balanced Dr/Cr entry may net to zero; that does not mean the PPE impact is zero.
2. Only direct PPE rows may enter direct_ppe_net_amount and direct_amount_checks.
   Direct PPE means original value/cost, accumulated depreciation, impairment, NBV,
   or net PPE. Counterparty accounts such as SG&A/management expense, AP, cash,
   tax, revenue, or other non-PPE accounts are indirect and must not create direct
   amount mismatches.
3. For Dr/Cr two-column layouts, derive signed_amount at row level from the row's
   account and Dr/Cr columns. Do not use the total net Dr/Cr balance as the PPE amount.
4. For direct rows, compare signed_amount with the matching guidance_adjustments
   row for the same PPE account and mapped adjustment column: audit-type adjustments
   map to audit_adjustment; book/management adjustments map to book_adjustment.
   If only the sign is reversed but absolute values agree, mark match=true and
   explain the sign convention in match_reason.
5. If Dr/Cr direction, sign convention, or account classification is unclear, set
   ppe_impact=unclear and assessment=unclear; do not create a direct mismatch from
   uncertain evidence.
"""


def _call_combined_review(config: LlmConfig, payload: dict[str, Any]) -> dict[str, Any] | None:
    user = _USER_COMBINED_TEMPLATE.format(
        payload=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    try:
        return chat_completion_json(
            config,
            system=_SYSTEM_COMBINED + _LEAD017_ADDITIONAL_SYSTEM,
            user=user,
        )
    except LlmClientError:
        return None


def _issues_from_review(
    lead: LeadSheetDataset,
    review: dict[str, Any],
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    layout = review.get("layout") if isinstance(review.get("layout"), dict) else {}
    layout_conf = str(layout.get("confidence", "")).lower()
    if layout_conf == "low" or str(layout.get("amount_layout", "")).lower() == "unknown":
        notes = str(layout.get("layout_notes", "")).strip()
        msg = "Lead 调整汇总表版式或金额列未能可靠识别"
        if notes:
            msg += f"；{notes}"
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_LAYOUT,
                field="adjustment_layout",
                severity=Severity.NEED_REVIEW,
                message=msg,
                suggestion="人工确认表头、借贷列与符号约定后，再与引导表勾稽。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=layout.get("anchor_row") if isinstance(layout.get("anchor_row"), int) else None,
                review_source="LLM辅助判断",
                llm_review_type="Lead调整汇总版式",
            )
        )

    assessment = str(review.get("assessment", "")).strip().lower()
    if assessment == "sufficient":
        return issues

    rationale = str(review.get("rationale", "")).strip()
    action = str(review.get("suggested_action", "")).strip()
    flags = review.get("cross_account_flags") or []
    checks = review.get("direct_amount_checks") or []

    if assessment == "insufficient":
        sev = Severity.WARN if _has_direct_mismatch(checks) else Severity.NEED_REVIEW
        msg = "Lead 调整汇总表语义上不足"
    else:
        sev = Severity.NEED_REVIEW
        msg = "Lead 调整汇总表需人工复核（版式或跨科目影响）"

    if rationale:
        msg += f"；{rationale}"
    if flags:
        msg += f"；跨科目提示 {len(flags)} 条"

    row0 = lead.adjustment_rows[0].source_row if lead.adjustment_rows else None
    issues.append(
        QcIssue(
            asset_id=None,
            rule_id=RULE_SEMANTIC,
            field="adjustment_semantic",
            severity=sev,
            message=msg,
            suggestion=action or "补充调整原因、编号分类、对 PPE 的影响说明及 Refer 索引。",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
            source_row=row0,
            review_source="LLM辅助判断",
            llm_review_type="Lead调整汇总恰当性(MT-003)",
        )
    )
    return issues


def _has_direct_mismatch(checks: list[Any]) -> bool:
    for c in checks:
        if not isinstance(c, dict):
            continue
        if c.get("match") is False:
            return True
    return False


def run_lead_adjustment_llm_review(
    lead: LeadSheetDataset,
    config: LlmConfig,
    *,
    workbook_path: str | None = None,
    deterministic_hints: list[dict[str, Any]] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> tuple[list[QcIssue], dict[str, Any] | None]:
    """
    调整汇总 LLM 复核入口。

    返回 (issues, raw_review)；issues 仅 WARN / NEED_REVIEW。
    """
    if not config.enabled or not should_review_adjustments(lead):
        return [], None

    grid_meta: dict[str, Any] | None = None
    if workbook_path:
        grid_meta = load_adjustment_grid_for_lead(workbook_path, lead)

    payload = build_adjustment_review_payload(
        lead,
        adjustment_grid=grid_meta,
        deterministic_hints=deterministic_hints,
        workbook_context=workbook_context,
    )

    if _llm_passes() != 1:
        # 分步模式留待 M3c-b；当前与合并 pass 相同
        pass

    review = _call_combined_review(config, payload)
    if not review:
        return [], None

    return _issues_from_review(lead, review), review


def build_lead_adjustment_issues(
    lead: LeadSheetDataset,
    config: LlmConfig,
    *,
    workbook_path: str | None = None,
    deterministic_hints: list[dict[str, Any]] | None = None,
    workbook_context: dict[str, Any] | None = None,
) -> list[QcIssue]:
    """仅返回 issues（兼容调用方）。"""
    issues, _ = run_lead_adjustment_llm_review(
        lead,
        config,
        workbook_path=workbook_path,
        deterministic_hints=deterministic_hints,
        workbook_context=workbook_context,
    )
    return issues


def extract_layout_and_rows_for_gating(review: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """供 LEAD-017 门控：从合并 review 结果取 layout 与 rows。"""
    layout = review.get("layout") if isinstance(review.get("layout"), dict) else None
    rows = review.get("rows") if isinstance(review.get("rows"), list) else []
    return layout, [r for r in rows if isinstance(r, dict)]
