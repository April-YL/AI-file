"""K.00 Lead Sheet 锚点分块识别（不依赖固定行号）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

# 扫描列宽：Lead 主标签多在 B 列，表头可至 O 列
_SCAN_LABEL_COLS = 6
_SCAN_HEADER_COLS = 18


class LeadBlockKind(str, Enum):
    BASIC_INFO = "basic_info"
    CRA_THRESHOLD = "cra_threshold"
    EXPECTATION = "expectation"
    MOVEMENT_TABLE = "movement_table"
    FLUCTUATION_NOTES = "fluctuation_notes"
    ADJUSTMENT_SUMMARY = "adjustment_summary"


@dataclass
class LeadBlock:
    """Lead 表内一个逻辑模块的边界（1-based 行号）。"""

    kind: LeadBlockKind
    anchor_row: int
    start_row: int
    end_row: int | None
    confidence: float
    anchor_text: str
    notes: list[str] = field(default_factory=list)


def _cell_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-（）()]", "", text.lower())


def _row_texts(row: tuple[Any, ...], max_col: int) -> list[str | None]:
    return [_cell_str(row[c]) if c < len(row) else None for c in range(max_col)]


def _label_in_cell(text: str, patterns: tuple[str, ...]) -> bool:
    n = _norm(text)
    if not n or len(n) > 60:
        return False
    for p in patterns:
        pn = _norm(p)
        if not pn:
            continue
        if len(pn) <= 4 and pn.isascii():
            if n == pn:
                return True
            continue
        if pn in n or n in pn:
            return True
    return False


def _find_anchor_rows(
    rows: Sequence[tuple[Any, ...]],
    patterns: tuple[str, ...],
    *,
    max_col: int = _SCAN_LABEL_COLS,
    max_row: int | None = None,
) -> list[tuple[int, str, int]]:
    """返回 (0-based row, matched text, col index)。"""
    limit = len(rows) if max_row is None else min(len(rows), max_row)
    hits: list[tuple[int, str, int]] = []
    for r in range(limit):
        for c in range(max_col):
            if c >= len(rows[r]):
                continue
            text = _cell_str(rows[r][c])
            if text and _label_in_cell(text, patterns):
                hits.append((r, text, c))
    return hits


def _find_header_row(
    rows: Sequence[tuple[Any, ...]],
    required: tuple[tuple[str, ...], ...],
    *,
    scan_rows: int = 120,
    max_col: int = _SCAN_HEADER_COLS,
) -> tuple[int | None, float]:
    """表头行：每 tuple 至少匹配一个 pattern 之一。"""
    best_row: int | None = None
    best_score = 0.0
    for r in range(min(scan_rows, len(rows))):
        cells = _row_texts(rows[r], max_col)
        matched_groups = 0
        for group in required:
            if any(
                text and _label_in_cell(text, group)
                for text in cells
            ):
                matched_groups += 1
        if matched_groups >= len(required):
            score = matched_groups / len(required)
            if score > best_score:
                best_score = score
                best_row = r
    return best_row, best_score


# ---- 锚点模式 -----------------------------------------------------------------
_BASIC_INFO_ANCHORS = ("客户名称", "clientname", "客户")
_CRA_ANCHORS = ("认定",)
_EXPECTATION_ANCHORS = ("账户变更", "预期及额外考虑", "预期分析")
_MOVEMENT_ANCHORS = ("总账科目编码", "期末账面数", "科目名称")
_FLUCTUATION_ANCHORS = ("波动说明",)
_ADJUSTMENT_ANCHORS = ("调整汇总表", "调整类型")


def detect_lead_blocks(rows: Sequence[tuple[Any, ...]]) -> list[LeadBlock]:
    """
    按锚点扫描 Lead 工作表，输出各模块近似边界。

    行号均为 1-based；``end_row`` 为 inclusive，None 表示至 sheet 末（或扫描末）。
    """
    if not rows:
        return []

    anchors: list[tuple[int, LeadBlockKind, str, float]] = []

    basic_hits = _find_anchor_rows(rows, _BASIC_INFO_ANCHORS, max_row=35)
    if basic_hits:
        r, text, _ = basic_hits[0]
        anchors.append((r, LeadBlockKind.BASIC_INFO, text, 0.9))

    cra_header, cra_score = _find_header_row(
        rows,
        (
            ("认定", "相关认定", "assertion"),
            ("cra", "combinedrisk", "风险", "风险评估"),
            ("tt", "测试阈值", "threshold", "各项认定", "所有相关认定"),
        ),
        scan_rows=80,
    )
    if cra_header is not None:
        cells = _row_texts(rows[cra_header], _SCAN_HEADER_COLS)
        label = next((t for t in cells if t and _label_in_cell(t, ("认定",))), "认定")
        anchors.append((cra_header, LeadBlockKind.CRA_THRESHOLD, label, max(0.7, cra_score)))

    exp_hits = _find_anchor_rows(rows, _EXPECTATION_ANCHORS, max_row=100)
    if exp_hits:
        # 优先「账户变更」表头行
        exp_hit = next((h for h in exp_hits if _label_in_cell(h[1], ("账户变更",))), exp_hits[0])
        r, text, _ = exp_hit
        anchors.append((r, LeadBlockKind.EXPECTATION, text, 0.85))

    mov_header, mov_score = _find_header_row(
        rows,
        (("期末账面数", "账面数"), ("科目名称", "总账科目编码")),
        scan_rows=150,
    )
    if mov_header is not None:
        cells = _row_texts(rows[mov_header], _SCAN_HEADER_COLS)
        label = next(
            (t for t in cells if t and _label_in_cell(t, ("期末账面数", "总账科目编码", "科目名称"))),
            "引导表",
        )
        anchors.append((mov_header, LeadBlockKind.MOVEMENT_TABLE, label, max(0.75, mov_score)))

    fluc_hits = _find_anchor_rows(rows, _FLUCTUATION_ANCHORS, max_row=180)
    if fluc_hits:
        r, text, _ = fluc_hits[0]
        anchors.append((r, LeadBlockKind.FLUCTUATION_NOTES, text, 0.8))

    adj_hits = _find_anchor_rows(rows, _ADJUSTMENT_ANCHORS, max_row=200)
    if adj_hits:
        r, text, _ = adj_hits[0]
        anchors.append((r, LeadBlockKind.ADJUSTMENT_SUMMARY, text, 0.75))

    if not anchors:
        return []

    # 去重：同 kind 保留最先出现的锚点
    seen: set[LeadBlockKind] = set()
    unique: list[tuple[int, LeadBlockKind, str, float]] = []
    for item in sorted(anchors, key=lambda x: x[0]):
        if item[1] in seen:
            continue
        seen.add(item[1])
        unique.append(item)

    blocks: list[LeadBlock] = []
    for i, (r0, kind, text, conf) in enumerate(unique):
        start = r0 + 1
        if kind == LeadBlockKind.BASIC_INFO:
            start = 1
        end0 = len(rows) - 1
        for j in range(i + 1, len(unique)):
            if unique[j][0] > r0:
                end0 = unique[j][0] - 1
                break
        if kind == LeadBlockKind.MOVEMENT_TABLE:
            start = r0 + 1
        notes: list[str] = []
        if i + 1 < len(unique):
            notes.append(f"下一块锚点: {unique[i + 1][2]!r} @ R{unique[i + 1][0] + 1}")
        blocks.append(
            LeadBlock(
                kind=kind,
                anchor_row=r0 + 1,
                start_row=start,
                end_row=end0 + 1,
                confidence=conf,
                anchor_text=text,
                notes=notes,
            )
        )
    return blocks


def block_for_kind(blocks: Sequence[LeadBlock], kind: LeadBlockKind) -> LeadBlock | None:
    return next((b for b in blocks if b.kind == kind), None)


def slice_rows_for_block(
    rows: Sequence[tuple[Any, ...]],
    block: LeadBlock | None,
) -> list[tuple[Any, ...]]:
    if block is None or not rows:
        return list(rows)
    start = max(0, block.start_row - 1)
    end = min(len(rows), block.end_row or len(rows))
    return list(rows[start:end])
