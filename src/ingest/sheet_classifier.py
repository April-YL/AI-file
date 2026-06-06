from __future__ import annotations

import re

from ingest.constants import CONTENT_SIGNATURES, SKIP_SHEET_PREFIXES
from ingest.header_detection import count_signature_fields, scan_rows_for_headers
from ingest.models import SheetKind


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def score_by_name(sheet_name: str) -> tuple[SheetKind, float, str | None]:
    """根据工作表名称返回 (kind, score 0-1, hint)。"""
    n = _norm_name(sheet_name)
    raw = sheet_name.strip()

    for prefix in SKIP_SHEET_PREFIXES:
        if raw == prefix or raw.startswith(prefix):
            return SheetKind.SKIP, 1.0, "skip_prefix"

    if "skywindsettingsheet" in n:
        return SheetKind.SKIP, 1.0, "skywind"

    # 顺序：更具体的先匹配
    if "折旧政策" in raw or "k.03.3" in n:
        return SheetKind.DEPRECIATION_POLICY, 0.9, "name_k033"
    if ("k.03.2" in n or "折旧测试" in raw) and ("byitem" in n.replace(" ", "") or "by item" in raw.lower()):
        return SheetKind.DEPRECIATION_TOD, 0.92, "name_dep_tod_byitem"
    if "k.03.2" in n or ("折旧测试" in raw and "tod" in n):
        return SheetKind.DEPRECIATION_TOD_SAMPLE, 0.75, "name_dep_tod_sample"
    if "k.03.1" in n or (n.endswith("sap") or " sap" in n):
        return SheetKind.SAP, 0.88, "name_sap"
    if "k.02.1a" in n or (
        "新增" in raw and any(x in raw for x in ("选样", "抽样")) and any(x in raw for x in ("输出", "结果"))
    ):
        return SheetKind.ADDITION_SAMPLE_OUTPUT, 0.9, "name_addition_sample_output"
    if "k.02.1" in n and "k.02.1b" not in n:
        return SheetKind.ADDITION_TEST, 0.9, "name_addition_test"
    if "新增" in raw and any(x in raw for x in ("测试", "细节")):
        return SheetKind.ADDITION_TEST, 0.86, "name_addition_test"
    if "新增清单" in raw or "k.02.1b" in n and "新增" in raw:
        return SheetKind.ADDITION_LIST, 0.9, "name_addition"
    if (
        "处置清单" in raw
        or "减少清单" in raw
        or ("k.02.2b" in n and ("处置" in raw or "减少" in raw or "报废" in raw))
    ):
        return SheetKind.DISPOSAL_LIST, 0.9, "name_disposal"
    if "fa list" in n or "固定资产清单" in raw or "资产清单" in raw:
        return SheetKind.FA_LIST, 0.88, "name_fa_list"
    if re.search(r"fa\s*list", raw, re.I) or "k.01.1" in n and "fa" in n:
        return SheetKind.FA_LIST, 0.85, "name_fa_list_variant"
    if "k.00" in n or "lead sheet" in n:
        return SheetKind.LEAD, 0.88, "name_lead"
    if "k.01" in n or ("agree" in n and "gl" in n) or "后推" in raw:
        return SheetKind.ROLLFORWARD, 0.85, "name_rollforward"
    if "汇总" in raw:
        return SheetKind.SUMMARY, 0.8, "name_summary"

    return SheetKind.UNCLASSIFIED, 0.0, None


def _resolve_name_over_content(
    *,
    name_kind: SheetKind,
    name_score: float,
    name_hint: str | None,
    content_kind: SheetKind,
    content_score: float,
    content_cells: list,
    header_row: int | None,
) -> tuple[SheetKind, float, float, float, str | None, int | None] | None:
    """名称明确的程序 sheet 不得被后推表头内容覆盖。"""
    if content_kind != SheetKind.ROLLFORWARD:
        return None

    min_hits: dict[SheetKind, tuple[float, int]] = {
        SheetKind.FA_LIST: (0.85, 3),
        SheetKind.ADDITION_LIST: (0.85, 2),
        SheetKind.DISPOSAL_LIST: (0.85, 2),
        SheetKind.SUMMARY: (0.75, 0),
        SheetKind.LEAD: (0.85, 1),
    }
    rule = min_hits.get(name_kind)
    if rule is None or name_score < rule[0]:
        return None

    if name_kind == SheetKind.SUMMARY:
        confidence = min(0.96, 0.55 * name_score + 0.35)
        return (
            SheetKind.SUMMARY,
            confidence,
            name_score,
            content_score,
            name_hint,
            header_row,
        )

    sig = CONTENT_SIGNATURES.get(name_kind, set())
    if not sig:
        return None
    hit = count_signature_fields(content_cells, sig, sheet_kind=name_kind)
    if hit < rule[1]:
        return None

    confidence = min(0.96, 0.35 * name_score + 0.45 * (hit / max(len(sig), 1)) + 0.2)
    return (
        name_kind,
        confidence,
        name_score,
        content_score,
        name_hint,
        header_row,
    )


def _rollforward_period_bonus(header_cells: list) -> float:
    """表头含期初/期末/本期变动等时抬高 K.01 与「仅有金额列的 FA list」的区分度。"""
    if not header_cells:
        return 0.0
    opening = any("期初" in str(t) for _, t in header_cells)
    ending = any("期末" in str(t) or "年末" in str(t) for _, t in header_cells)
    movement_tokens = (
        "本期增加",
        "本期减少",
        "购置",
        "处置",
        "报废",
        "计提折旧",
        "本期折旧",
        "审计调整",
        "账表调整",
    )
    movement = any(any(m in str(t) for m in movement_tokens) for _, t in header_cells)
    return 0.15 * (int(opening) + int(ending) + int(movement))


def score_by_content(
    rows: list,
    sheet_kind_hint: SheetKind | None = None,
) -> tuple[SheetKind, float, int | None, list]:
    """根据表头内容对各类型打分，返回最佳类型。"""
    best_kind = SheetKind.UNCLASSIFIED
    best_score = 0.0
    best_row: int | None = None
    best_cells: list = []

    kinds_to_try = list(CONTENT_SIGNATURES.keys())
    if sheet_kind_hint and sheet_kind_hint != SheetKind.UNCLASSIFIED:
        kinds_to_try = [sheet_kind_hint] + [k for k in kinds_to_try if k != sheet_kind_hint]

    for kind in kinds_to_try:
        sig = CONTENT_SIGNATURES.get(kind, set())
        if not sig:
            continue
        header_row, cells, _ = scan_rows_for_headers(rows, sheet_kind=kind)
        if not cells:
            continue
        hit = count_signature_fields(cells, sig, sheet_kind=kind)
        base_score = hit / max(len(sig), 1)
        tie_score = base_score
        if kind == SheetKind.ROLLFORWARD:
            tie_score = min(1.35, base_score + _rollforward_period_bonus(cells))
        score = tie_score
        if score > best_score:
            best_score = score
            best_kind = kind
            best_row = header_row
            best_cells = cells

    # by item 折旧表：字段更全则提升为 DEPRECIATION_TOD
    if best_kind in (SheetKind.DEPRECIATION_TOD, SheetKind.DEPRECIATION_TOD_SAMPLE):
        full_sig = CONTENT_SIGNATURES[SheetKind.DEPRECIATION_TOD]
        hit = count_signature_fields(best_cells, full_sig, SheetKind.DEPRECIATION_TOD)
        if hit >= 6:
            best_kind = SheetKind.DEPRECIATION_TOD
            best_score = max(best_score, 0.85)

    return best_kind, min(1.0, best_score), best_row, best_cells


def classify_sheet(
    sheet_name: str,
    rows: list,
) -> tuple[SheetKind, float, float, float, str | None, int | None]:
    """
    综合名称与内容分类。
    返回 (kind, confidence, name_score, content_score, name_hint, header_row).
    """
    name_kind, name_score, name_hint = score_by_name(sheet_name)
    if name_kind == SheetKind.SKIP:
        return name_kind, 1.0, name_score, 0.0, name_hint, None

    content_kind, content_score, header_row, content_cells = score_by_content(
        rows,
        sheet_kind_hint=name_kind if name_score >= 0.7 else None,
    )

    locked = _resolve_name_over_content(
        name_kind=name_kind,
        name_score=name_score,
        name_hint=name_hint,
        content_kind=content_kind,
        content_score=content_score,
        content_cells=content_cells,
        header_row=header_row,
    )
    if locked is not None:
        return locked

    # K.02.1/K.02.1a 是程序页，不应因包含资产编号/原值等测试表头被当作 FA list 或 K.01。
    if name_kind in (SheetKind.ADDITION_TEST, SheetKind.ADDITION_SAMPLE_OUTPUT) and name_score >= 0.85:
        header_row, _, _ = scan_rows_for_headers(rows, sheet_kind=name_kind)
        return name_kind, min(0.95, name_score * 0.9), name_score, content_score, name_hint, header_row

    # 名称明确为 FA list 时，不因仅含金额列而被判为后推表（K.01 不会命名为 FA list）
    if (
        name_kind == SheetKind.FA_LIST
        and name_score >= 0.85
        and content_kind == SheetKind.ROLLFORWARD
    ):
        fa_sig = CONTENT_SIGNATURES[SheetKind.FA_LIST]
        fa_hit = count_signature_fields(content_cells, fa_sig, SheetKind.FA_LIST)
        if fa_hit >= 3:
            confidence = min(0.96, 0.35 * name_score + 0.45 * (fa_hit / max(len(fa_sig), 1)) + 0.2)
            return (
                SheetKind.FA_LIST,
                confidence,
                name_score,
                content_score,
                name_hint,
                header_row,
            )

    # 内容优先；名称一致时加分
    if content_score >= 0.45 and content_kind != SheetKind.UNCLASSIFIED:
        kind = content_kind
        confidence = min(0.95, 0.5 * content_score + 0.3 * name_score + 0.2)
        if name_kind == content_kind and name_score >= 0.7:
            confidence = min(0.98, confidence + 0.15)
        elif name_kind != content_kind and name_score >= 0.7:
            confidence = max(confidence, content_score * 0.9)
        return kind, confidence, name_score, content_score, name_hint, header_row

    if name_score >= 0.75 and name_kind != SheetKind.UNCLASSIFIED:
        header_row, _, _ = scan_rows_for_headers(rows, sheet_kind=name_kind)
        confidence = name_score * 0.85
        return name_kind, confidence, name_score, content_score, name_hint, header_row

    return SheetKind.UNCLASSIFIED, max(name_score, content_score) * 0.5, name_score, content_score, name_hint, header_row
