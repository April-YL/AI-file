from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import openpyxl

from ingest.records import FaListDataset
from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from ingest.reconciliation import ReconciliationCheck
from ingest.workbook_reader import read_worksheet_rows
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount
from rules.psp_completion import WaiverSemanticReview, normalize_execution_status
from rules.psp_sheet_matcher import find_matching_sheet, rank_sheet_candidates

_WAIVER_SYSTEM = """你是固定资产审计底稿复核助手。仅判断汇总页“选否/不执行理由”是否充分。
判断时必须贴近固定资产 K1 底稿实际执行口径；引入 LLM 后仍需人工确认复核。
TE、TT、SAD 均指 K.00 Lead Sheet 中读取到的对应金额；使用底稿内读取到的数据，不要求与外部系统或外部数据比对。

输出含义：
- sufficient：理由已有可复核的业务原因、金额/性质风险依据、或替代证据/程序，且与输入摘录不冲突。
- insufficient：理由缺少可复核依据，或与输入摘录冲突。
- unclear：输入摘录不足以确认充分性，或属于未覆盖情形，需要人工打开底稿复核。

必须判 insufficient 的典型情形包括但不限于：
1) 仅写“无需执行”“金额小”“N/A”“NA”“N/a”“不重大”“无减值迹象”等空泛结论，且无业务原因、金额依据、性质风险判断、替代程序或证据来源；
2) 声称“本期无新增/无处置/无相关交易”，但输入摘录显示 K.01 Agree SL to GL 的表1后推明细表存在对应新增、处置或变动；
3) 声称基于金额不重大，但未说明与底稿内 TE/TT/SAD、总体金额、单项金额或性质风险的关系；
4) 减值测试不执行理由仅写“无减值迹象”，但未说明减值迹象识别程序、判断原因或支持文件；
5) 其他只有结论、没有可复核判断依据的情况。

可接受口径：
1) 新增/处置测试：理由基于审计风险，从金额和性质两方面说明。TE、TT、SAD 不是并列标准，必须按以下判断树逐级判断，不得混用条件：
   第一层：如理由明确说明新增/处置金额小于 K.00 Lead Sheet 的 SAD，则金额层面可接受。除非输入摘录显示存在性质异常项，否则不得再要求补充 TE 或 TT。
   第二层：如理由明确说明新增/处置金额小于 K.00 Lead Sheet 的 TT，则金额层面可接受；但仍需说明或能从输入摘录判断不存在性质异常项。不得再要求补充 TE。
   第三层：如理由仅说明总体金额、处置资产净值或新增金额小于 K.00 Lead Sheet 的 TE，不能直接认为充分；还必须同时说明无单项金额大于 K.00 Lead Sheet 的 TT，且无性质异常项。缺少任一项，应判断为 insufficient 或 unclear。
   第四层：如理由仅写“金额小”“不重大”“低于重要性”等，未指明 SAD/TT/TE 或没有可复核金额依据，应判断为 insufficient 或 unclear。
   禁止漂移判断：已明确小于 SAD 时，不得仍要求补充 TT/TE；已明确小于 TT 且无性质异常项时，不得仍要求补充 TE；不得仅因未写“替代程序”就否定金额豁免理由；性质异常项必须结合程序主题判断。
2) 明确说明“本期无新增/无处置/无相关交易”，且输入摘录能支持后推明细表无对应新增、处置或变动。
3) 减值测试：理由需包含结论和判断原因，可参考：使用审计过程中获得的信息识别减值迹象；可使用 PSP Canvas form K.04 或 SWP 减值迹象识别；如有减值迹象，评价管理层假设、未来现金流等减值评估并测算减值金额；检查是否存在固定资产减值准备转回且确认以后期间没有转回。

如果输入没有提供 K.01 后推明细表、K.00 Lead Sheet 的 TE/TT/SAD 或支持证据摘录，不得编造；应根据已有理由本身判断，证据不足时返回 unclear 并说明需人工核对。
输出 rationale 时，必须说明命中 SAD/TT/TE 哪一层判断，以及当前层级缺少什么信息；suggested_action 只补充当前层级缺失的信息，不提出无关要求。
只输出 JSON。"""

_SHEET_SYSTEM = """你是固定资产底稿索引匹配助手。根据汇总页程序信息和候选工作表摘录，
判断是否存在可支持的目标工作表。仅输出 JSON，不要 markdown。"""


def review_waiver_reason_with_llm(
    row: PspProgramRow,
    config: LlmConfig,
    *,
    semantic_context: dict[str, Any] | None = None,
) -> WaiverSemanticReview | None:
    waiver = (row.waiver_reason or "").strip()
    if not waiver:
        return None
    payload = {
        "procedure_name": row.procedure_name,
        "sheet_ref": row.sheet_ref,
        "execution_status": row.execution_status,
        "waiver_reason": waiver,
        "notes": row.notes,
        "workbook_context": semantic_context or {},
    }
    user = (
        "请判断该汇总页程序的不执行理由是否充分。返回 JSON：\n"
        '{ "adequacy":"sufficient|insufficient|unclear", "rationale":"", "suggested_action":"" }\n'
        f"输入：{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        out = chat_completion_json(config, system=_WAIVER_SYSTEM, user=user)
    except LlmClientError:
        return None
    adequacy = str(out.get("adequacy", "")).strip().lower()
    if adequacy not in {"sufficient", "insufficient", "unclear"}:
        return None
    return WaiverSemanticReview(
        adequacy=adequacy,  # type: ignore[arg-type]
        rationale=str(out.get("rationale", "")).strip(),
        suggested_action=str(out.get("suggested_action", "")).strip(),
    )


def review_waiver_reasons_batch_with_llm(
    rows: list[PspProgramRow],
    config: LlmConfig,
    *,
    semantic_context: dict[str, Any] | None = None,
) -> dict[int, WaiverSemanticReview]:
    targets = [
        (idx, row)
        for idx, row in enumerate(rows)
        if (row.waiver_reason or "").strip()
    ]
    if not targets:
        return {}
    payload = {
        "programs": [
            {
                "row_id": idx,
                "procedure_name": row.procedure_name,
                "sheet_ref": row.sheet_ref,
                "execution_status": row.execution_status,
                "waiver_reason": row.waiver_reason,
                "notes": row.notes,
                "source_row": row.source_row,
            }
            for idx, row in targets
        ],
        "workbook_context": semantic_context or {},
    }
    user = (
        "请逐条判断以下汇总页程序的不执行理由是否充分。返回 JSON：\n"
        '{ "reviews": ['
        '{ "row_id": 0, "adequacy":"sufficient|insufficient|unclear", '
        '"rationale":"", "suggested_action":"" }'
        "] }\n"
        f"输入：{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        out = chat_completion_json(config, system=_WAIVER_SYSTEM, user=user)
    except LlmClientError:
        return {}
    raw_reviews = out.get("reviews")
    if not isinstance(raw_reviews, list):
        return {}
    reviews: dict[int, WaiverSemanticReview] = {}
    valid_ids = {idx for idx, _ in targets}
    for item in raw_reviews:
        if not isinstance(item, dict):
            continue
        try:
            row_id = int(item.get("row_id"))
        except (TypeError, ValueError):
            continue
        if row_id not in valid_ids:
            continue
        adequacy = str(item.get("adequacy", "")).strip().lower()
        if adequacy not in {"sufficient", "insufficient", "unclear"}:
            continue
        reviews[row_id] = WaiverSemanticReview(
            adequacy=adequacy,  # type: ignore[arg-type]
            rationale=str(item.get("rationale", "")).strip(),
            suggested_action=str(item.get("suggested_action", "")).strip(),
        )
    return reviews


def build_waiver_semantic_context(
    *,
    lead: LeadSheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
    addition_list: FaListDataset | None = None,
    disposal_list: FaListDataset | None = None,
    reconciliations: list[ReconciliationCheck] | None = None,
    workbook_sheet_titles: list[str] | None = None,
) -> dict[str, Any]:
    """构造汇总页选否理由语义复核上下文，避免 LLM 只看单行文字。"""
    context: dict[str, Any] = {}
    if lead is not None:
        context["lead"] = _lead_context(lead)
    if rollforward is not None:
        context["k01_rollforward"] = _rollforward_context(rollforward)
    if addition_list is not None:
        context["addition_list"] = _asset_list_context(addition_list)
    if disposal_list is not None:
        context["disposal_list"] = _asset_list_context(disposal_list)
    if reconciliations:
        context["reconciliations"] = [
            c.to_dict() for c in reconciliations[:8]
        ]
    if workbook_sheet_titles:
        context["workbook_sheets"] = workbook_sheet_titles[:80]
    return context


def _lead_context(lead: LeadSheetDataset) -> dict[str, Any]:
    return {
        "source_sheet": lead.source_sheet,
        "materiality": [
            {
                "field_key": m.field_key,
                "label": m.label,
                "workpaper_value": m.workpaper_value,
                "canvas_value": m.canvas_value,
                "source_row": m.source_row,
            }
            for m in lead.materiality
        ],
        "basic_materiality_fields": [
            {
                "field_key": f.field_key,
                "label": f.label,
                "value": f.value,
                "source_row": f.source_row,
            }
            for f in lead.basic_info_fields
            if f.field_key in {"pm", "te", "sad"}
        ],
        "cra_tt_rows": [
            {
                "assertion": r.assertion,
                "cra": r.cra,
                "tt": r.tt,
                "tt_overall": r.tt_overall,
                "source_row": r.source_row,
            }
            for r in lead.cra_rows[:12]
        ],
        "expectations": [
            {
                "account_change": e.account_change,
                "expectation": e.expectation,
                "source_row": e.source_row,
            }
            for e in lead.expectations[:12]
        ],
        "movement_rows": [
            {
                "account_label": r.account_label,
                "sheet_ref": r.sheet_ref,
                "values": r.values,
                "source_row": r.source_row,
            }
            for r in lead.movement_rows[:8]
        ],
        "fluctuation_notes": lead.fluctuation_notes,
        "notes": lead.notes[:8],
    }


def _rollforward_context(rollforward: RollforwardSheetDataset) -> dict[str, Any]:
    return {
        "source_sheet": rollforward.source_sheet,
        "has_movement_rows": rollforward.has_movement_rows,
        "opening_totals": _decimal_dict(rollforward.opening_totals),
        "ending_totals": _decimal_dict(rollforward.ending_totals),
        "section_presence": rollforward.section_presence,
        "section_evidence": rollforward.section_evidence,
        "tb_reconciliation_detected": rollforward.tb_reconciliation_detected,
        "tb_difference_values": [str(v) for v in rollforward.tb_difference_values[:8]],
        "tb_notes_text": rollforward.tb_notes_text,
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


def _decimal_dict(values: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in values.items() if v is not None}


def build_sheet_semantic_issues(
    dataset: SummarySheetDataset,
    config: LlmConfig,
    *,
    workbook_path: str,
    workbook_sheet_titles: list[str],
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    if not workbook_sheet_titles:
        return issues

    for row in dataset.programs:
        if normalize_execution_status(row.execution_status) != "yes":
            continue
        ref = (row.sheet_ref or "").strip()
        if not ref:
            continue

        matched, score, _ = find_matching_sheet(ref, workbook_sheet_titles)
        if matched and score >= 0.72:
            continue

        candidates = rank_sheet_candidates(ref, workbook_sheet_titles, top_k=3, min_score=0.35)
        if not candidates:
            continue
        reviewed = _review_sheet_match(row, candidates, workbook_path, config)
        if reviewed is None:
            continue
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id="psp_completion",
                field="sheet_ref_semantic",
                severity=Severity.NEED_REVIEW,
                message=reviewed["message"],
                suggestion=reviewed["suggestion"],
                procedure_code="SUMMARY",
                source_sheet=dataset.source_sheet or "汇总",
                source_row=row.source_row,
                review_source="LLM辅助判断",
                llm_review_type="汇总页程序页语义匹配",
            )
        )
    return issues


def _review_sheet_match(
    row: PspProgramRow,
    candidates: list[tuple[str, float, str]],
    workbook_path: str,
    config: LlmConfig,
) -> dict[str, str] | None:
    preview = _build_candidate_preview(workbook_path, [c[0] for c in candidates])
    if not preview:
        return None
    payload = {
        "procedure_name": row.procedure_name,
        "sheet_ref": row.sheet_ref,
        "execution_status": row.execution_status,
        "notes": row.notes,
        "candidates": [
            {"sheet_title": t, "score": round(s, 3), "reason": r}
            for t, s, r in candidates
        ],
        "sheet_preview": preview,
    }
    user = (
        "请判断候选工作表是否支持该程序页引用。返回 JSON：\n"
        '{ "assessment":"match_supported|uncertain|no_support", "chosen_sheet":"", '
        '"rationale":"", "suggested_action":"" }\n'
        f"输入：{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        out = chat_completion_json(config, system=_SHEET_SYSTEM, user=user)
    except LlmClientError:
        return None
    assessment = str(out.get("assessment", "")).strip().lower()
    if assessment not in {"match_supported", "uncertain", "no_support"}:
        return None
    chosen = str(out.get("chosen_sheet", "")).strip()
    rationale = str(out.get("rationale", "")).strip()
    suggestion = str(out.get("suggested_action", "")).strip() or "人工打开候选程序页并核对索引。"

    if assessment == "match_supported" and chosen:
        msg = (
            f"程序「{row.procedure_name}」引用「{row.sheet_ref}」名称匹配较弱；"
            f"结合内容更可能对应「{chosen}」"
        )
    elif assessment == "no_support":
        msg = (
            f"程序「{row.procedure_name}」引用「{row.sheet_ref}」在候选程序页中未见明显支持证据"
        )
    else:
        msg = (
            f"程序「{row.procedure_name}」引用「{row.sheet_ref}」候选页语义判断不确定"
        )
    if rationale:
        msg += f"；模型提示：{rationale}"
    return {"message": msg, "suggestion": suggestion}


def _build_candidate_preview(workbook_path: str, sheet_titles: list[str]) -> list[dict[str, Any]]:
    path = Path(workbook_path)
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        out: list[dict[str, Any]] = []
        for sheet in sheet_titles:
            if sheet not in wb.sheetnames:
                continue
            rows = read_worksheet_rows(wb[sheet], max_rows=14)
            lines: list[str] = []
            for row in rows:
                vals = [str(v).strip() for v in row[:8] if v is not None and str(v).strip()]
                if vals:
                    lines.append(" | ".join(vals))
                if len(lines) >= 8:
                    break
            out.append({"sheet_title": sheet, "preview_lines": lines})
        return out
    finally:
        wb.close()
