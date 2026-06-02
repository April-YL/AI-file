from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import openpyxl

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from ingest.workbook_reader import read_worksheet_rows
from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from rules.models import QcIssue, Severity
from rules.psp_completion import WaiverSemanticReview, normalize_execution_status
from rules.psp_sheet_matcher import find_matching_sheet, rank_sheet_candidates

_WAIVER_SYSTEM = """你是固定资产审计底稿复核助手。仅判断汇总页“选否/不执行理由”是否充分。
判断时必须贴近固定资产 K1 底稿实际执行口径；引入 LLM 后仍需人工确认复核。
TE、TT、SAD 使用底稿内读取到的数据，不要求与外部系统或外部数据比对。

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
1) 新增/处置测试：理由基于审计风险，从金额和性质两方面说明，并按以下递进口径之一判断 sufficient：
   A. 总体金额小于底稿内 TE，且无单项大于底稿内 TT 的资产，且无性质异常项；
   B. 新增/处置金额小于底稿内 TT，且无性质异常项；
   C. 新增/处置金额小于底稿内 SAD。
   仅写“总体金额小于 TE”“处置资产净值小于 TE”“新增金额小于 TE”等，不足以判断充分；若没有同时说明无单项大于 TT 且无性质异常项，也没有说明金额小于 SAD，应判断为 insufficient 或 unclear。
2) 明确说明“本期无新增/无处置/无相关交易”，且输入摘录能支持后推明细表无对应新增、处置或变动。
3) 减值测试：理由需包含结论和判断原因，可参考：使用审计过程中获得的信息识别减值迹象；可使用 PSP Canvas form K.04 或 SWP 减值迹象识别；如有减值迹象，评价管理层假设、未来现金流等减值评估并测算减值金额；检查是否存在固定资产减值准备转回且确认以后期间没有转回。

如果输入没有提供 K.01 后推明细表、底稿内 TE/TT/SAD 或支持证据摘录，不得编造；应根据已有理由本身判断，证据不足时返回 unclear 并说明需人工核对。
只输出 JSON。"""

_SHEET_SYSTEM = """你是固定资产底稿索引匹配助手。根据汇总页程序信息和候选工作表摘录，
判断是否存在可支持的目标工作表。仅输出 JSON，不要 markdown。"""


def review_waiver_reason_with_llm(
    row: PspProgramRow,
    config: LlmConfig,
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
