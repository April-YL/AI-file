"""汇总页「程序页」引用与工作簿实际 sheet 名称的模糊匹配（PSP 已执行时的形式勾稽）。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Sequence

import openpyxl

from ingest.workbook_reader import read_worksheet_rows

_INTERNAL_HINTS = (
    "ds_internal_",
    "skywindsettingsheet",
)

# 低于此分则不返回匹配（与 psp_completion 勾稽阈值一致，避免弱相似误报）
_MIN_MATCH_SCORE_RETURN = 0.48


def is_likely_internal_sheet(name: str) -> bool:
    n = name.strip().lower().replace(" ", "")
    if name.strip().startswith("~"):
        return True
    return any(n.startswith(h) for h in _INTERNAL_HINTS)


def _norm_title(s: str) -> str:
    t = re.sub(r"\s+", " ", str(s).strip().lower())
    t = t.replace("（", "(").replace("）", ")")
    t = re.sub(r"[-_]\s*\d{2,4}\s*$", "", t)
    return t.rstrip("-_ ").strip()


def ref_query_strings(ref: str) -> list[str]:
    """从程序页单元格拆出若干匹配用子串（去全角括号后说明）。"""
    ref = str(ref).strip()
    if not ref:
        return []
    out: list[str] = [ref]
    for sep in ("（", "("):
        if sep in ref:
            head = ref.split(sep, 1)[0].strip()
            if head and head != ref:
                out.append(head)
            break
    seen: dict[str, None] = {}
    result: list[str] = []
    for p in out:
        p = p.strip()
        if p and p not in seen:
            seen[p] = None
            result.append(p)
    return result


def _k_tokens(s: str) -> set[str]:
    return set(re.findall(r"k\.\d+(?:\.\d+)*[a-z]?", _norm_title(s)))


def _best_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def find_matching_sheet(
    ref: str | None,
    workbook_sheet_titles: Sequence[str],
) -> tuple[str | None, float, str]:
    """
    将汇总页「程序页」文本与 workbook 工作表名称对齐。

    返回 (匹配到的**原始**表名, 置信度 0~1, 原因码)。
    """
    titles = [t for t in workbook_sheet_titles if t and not is_likely_internal_sheet(t)]
    if not ref or not str(ref).strip() or not titles:
        return None, 0.0, "empty_ref_or_titles"

    best_title: str | None = None
    best_score = 0.0
    best_reason = "no_match"

    for rq in ref_query_strings(ref):
        nr = _norm_title(rq)
        if len(nr) < 2:
            continue
        k_ref = _k_tokens(nr)
        for orig in titles:
            nt = _norm_title(orig)
            if not nt:
                continue
            # 规范一致（含去掉 -24 等后缀）
            if nr == nt:
                return orig, 1.0, "exact_normalized"
            if nr in nt or nt in nr:
                shorter, longer = (nr, nt) if len(nr) <= len(nt) else (nt, nr)
                cov = len(shorter) / max(len(longer), 1)
                sc = 0.86 + min(0.12, 0.12 * cov)
                if sc > best_score:
                    best_score, best_title, best_reason = sc, orig, "substring"
                continue
            ratio = _best_ratio(nr, nt)
            k_bonus = 0.0
            if k_ref:
                k_sheet = _k_tokens(nt)
                if k_ref & k_sheet:
                    k_bonus = 0.15
            sc = min(0.97, ratio + k_bonus * (1.0 - ratio * 0.5))
            if sc > best_score:
                best_score, best_title, best_reason = sc, orig, "fuzzy_ratio"

    if best_title is None:
        return None, 0.0, "no_match"
    if best_score < _MIN_MATCH_SCORE_RETURN:
        return None, 0.0, "below_threshold"
    return best_title, best_score, best_reason


def rank_sheet_candidates(
    ref: str | None,
    workbook_sheet_titles: Sequence[str],
    *,
    top_k: int = 3,
    min_score: float = 0.35,
) -> list[tuple[str, float, str]]:
    """
    为程序页引用返回候选底稿页列表，供语义复核使用。

    返回项：(原始表名, 置信度 0~1, 原因码)。
    """
    titles = [t for t in workbook_sheet_titles if t and not is_likely_internal_sheet(t)]
    if not ref or not str(ref).strip() or not titles:
        return []

    best_by_title: dict[str, tuple[float, str]] = {}
    for rq in ref_query_strings(ref):
        nr = _norm_title(rq)
        if len(nr) < 2:
            continue
        k_ref = _k_tokens(nr)
        for orig in titles:
            nt = _norm_title(orig)
            if not nt:
                continue
            reason = "fuzzy_ratio"
            if nr == nt:
                sc = 1.0
                reason = "exact_normalized"
            elif nr in nt or nt in nr:
                shorter, longer = (nr, nt) if len(nr) <= len(nt) else (nt, nr)
                cov = len(shorter) / max(len(longer), 1)
                sc = 0.86 + min(0.12, 0.12 * cov)
                reason = "substring"
            else:
                ratio = _best_ratio(nr, nt)
                k_bonus = 0.0
                if k_ref:
                    k_sheet = _k_tokens(nt)
                    if k_ref & k_sheet:
                        k_bonus = 0.15
                sc = min(0.97, ratio + k_bonus * (1.0 - ratio * 0.5))
            prev = best_by_title.get(orig)
            if prev is None or sc > prev[0]:
                best_by_title[orig] = (sc, reason)

    ranked = [
        (title, score, reason)
        for title, (score, reason) in best_by_title.items()
        if score >= min_score
    ]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def count_non_empty_cells(
    workbook_path: str | Path,
    sheet_title: str,
    *,
    max_rows: int = 40,
) -> int:
    """用于判断底稿页是否异常空表（仅可读范围内）。"""
    path = Path(workbook_path)
    if path.suffix.lower() not in (".xlsx", ".xlsm", ".xlsb"):
        return -1
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_title not in wb.sheetnames:
            return -1
        rows = read_worksheet_rows(wb[sheet_title], max_rows=max_rows)
    finally:
        wb.close()
    n = 0
    for row in rows:
        for c in row:
            if c is None:
                continue
            if str(c).strip():
                n += 1
    return n
