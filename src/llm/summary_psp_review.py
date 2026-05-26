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

_WAIVER_SYSTEM = """你是固定资产审计底稿复核助手。仅判断“不执行理由”是否充分。
判断标准（依据 SOP 汇总页进阶提示）：
1) 需说明不执行的业务/风险原因，而不是只写“金额小/无需执行”；
2) 需体现阈值口径（TE/TT/SAD）或风险评估逻辑；
3) 如不执行标准程序，应说明替代程序或其他证据来源；
4) 不确定时返回 unclear，不得编造。
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
