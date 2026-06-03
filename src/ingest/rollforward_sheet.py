"""K.01 后推表解析：表头映射 + 合计行/明细汇总。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl

from ingest.field_mapping import map_headers
from ingest.header_detection import scan_rows_for_headers
from ingest.models import (
    AssetRecord,
    FieldMapping,
    RollforwardColumnBinding,
    RollforwardLayoutProfile,
    RollforwardPeriodRole,
    SheetKind,
)
from ingest.sheet_loader import SheetLoadCandidate
from ingest.records import parse_fa_list_rows
from ingest.sheet_loader import find_sheets_by_kind
from ingest.workbook_reader import read_worksheet_rows
from rules.parsing import parse_amount

TOTAL_ROW_PATTERN = re.compile(r"(合计|总计|期末余额|账面余额合计|Grand\s*Total)", re.I)

# K.01 六区块标准顺序（用于锚点行序校验）
K01_SECTION_IDS: tuple[str, ...] = (
    "b1_bkd_main_table",
    "b2_movement_tb_reconciliation",
    "b3_table2_fa_summary",
    "b4_table3_check_with_table1",
    "b5_table4_depreciation_pl",
    "b6_notes_investigation_routing",
)


@dataclass
class K01SectionRegion:
    """K.01 工作表内某一标准区块的行范围（1-based，含首尾）。"""

    section_id: str
    anchor_row: int | None = None
    start_row: int | None = None
    end_row: int | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class RollforwardSheetDataset:
    """K.01 后推表解析结果（明细行 + 合计行 + 列绑定）。

    `amount_column_bindings`：金额口径 ×（期初 / 本期变动 / 期末）语义，供规则层判断列完整性。
    多期并列时，`detail_records` 仍沿用单列映射（每标准字段一列），以合计行 + 绑定为准勾稽期末/期初。
    """

    source_file: str
    source_sheet: str
    header_row: int | None
    mapped_fields: list[FieldMapping]
    amount_column_bindings: list[RollforwardColumnBinding] = field(default_factory=list)
    detail_records: list[AssetRecord] = field(default_factory=list)
    opening_totals: dict[str, Decimal | None] = field(default_factory=dict)
    ending_totals: dict[str, Decimal | None] = field(default_factory=dict)
    total_row: int | None = None
    layout_profile: RollforwardLayoutProfile = RollforwardLayoutProfile.UNRECOGNIZED
    has_movement_rows: bool = False
    section_presence: dict[str, bool] = field(default_factory=dict)
    section_evidence: dict[str, list[str]] = field(default_factory=dict)
    section_regions: dict[str, K01SectionRegion] = field(default_factory=dict)
    section_conflicts: list[str] = field(default_factory=list)
    recognition_confidence: float = 0.0
    table2_amount_count: int = 0
    table3_check_values: list[Decimal] = field(default_factory=list)
    table3_check_row: int | None = None
    tb_reconciliation_detected: bool = False
    tb_reconciliation_confidence: float = 0.0
    tb_difference_values: list[Decimal] = field(default_factory=list)
    tb_difference_row: int | None = None
    tb_notes_text_present: bool = False
    tb_notes_row: int | None = None
    tb_notes_text: str | None = None
    table4_pl_amounts: list[Decimal] = field(default_factory=list)
    table4_pl_total: Decimal | None = None
    table4_pl_total_row: int | None = None
    table4_rollforward_depreciation: Decimal | None = None
    table4_rollforward_depreciation_row: int | None = None
    table4_difference: Decimal | None = None
    table4_difference_row: int | None = None
    table4_notes_text_present: bool = False
    table4_notes_row: int | None = None
    table4_notes_text: str | None = None
    notes: list[str] = field(default_factory=list)


def _cell_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _row_has_total_label(row: tuple[Any, ...], *, max_cols: int = 6) -> bool:
    for val in row[:max_cols]:
        text = _cell_str(val)
        if text and TOTAL_ROW_PATTERN.search(text):
            return True
    return False


def _amount_at_col(row: tuple[Any, ...], col_index: int) -> Decimal | None:
    if col_index <= 0 or col_index > len(row):
        return None
    return parse_amount(_cell_str(row[col_index - 1]))


def _extract_totals_from_row(
    row: tuple[Any, ...],
    col_by_field: dict[str, int],
) -> dict[str, Decimal | None]:
    totals: dict[str, Decimal | None] = {}
    for field_name in ("original_value", "accumulated_depreciation", "impairment_provision", "net_value"):
        col = col_by_field.get(field_name)
        if col is not None:
            totals[field_name] = _amount_at_col(row, col)
    return totals


def _sum_records(records: list[AssetRecord], field_name: str) -> Decimal | None:
    total = Decimal("0")
    seen = False
    for rec in records:
        val = parse_amount(getattr(rec, field_name, None))
        if val is not None:
            total += val
            seen = True
    return total if seen else None


def _infer_rollforward_measure(header_text: str) -> str | None:
    """从表头推断金额口径（不含仅「交易类别」等非金额列）。"""
    raw = str(header_text).strip()
    if not raw:
        return None
    compact = re.sub(r"\s+", "", raw)
    if "累计折旧" in raw or "累折" in compact:
        return "accumulated_depreciation"
    if "减值" in raw:
        return "impairment_provision"
    if "净值" in raw or "账面价值" in raw or "账面净值" in raw or raw.endswith("净额"):
        return "net_value"
    if "原值" in raw or "入账价值" in raw:
        return "original_value"
    if "计提折旧" in raw or "本期折旧" in raw or "折旧费用" in raw:
        return "accumulated_depreciation"
    if "折旧" in raw and "原值" not in raw:
        return "accumulated_depreciation"
    return None


def _infer_rollforward_period_role(header_text: str) -> RollforwardPeriodRole:
    raw = str(header_text).strip()
    if not raw:
        return RollforwardPeriodRole.UNKNOWN
    if "期初" in raw:
        return RollforwardPeriodRole.OPENING
    if "期末" in raw or "年末" in raw:
        return RollforwardPeriodRole.ENDING
    if "变动金额" in raw or "变动比例" in raw:
        return RollforwardPeriodRole.MOVEMENT
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
        "其他增加",
        "其他减少",
        "合并增加",
        "企业合并",
        "划分为持有待售",
        "持有待售",
    )
    if any(tok in raw for tok in movement_tokens):
        return RollforwardPeriodRole.MOVEMENT
    if raw.startswith("本期") or raw.startswith("本年"):
        return RollforwardPeriodRole.MOVEMENT
    return RollforwardPeriodRole.UNKNOWN


def _period_role_from_block_label(text: str) -> RollforwardPeriodRole:
    """表头上一行时期块标签（审2/审3、表2/表3 等）。"""
    raw = str(text).strip()
    if not raw or len(raw) > 40:
        return RollforwardPeriodRole.UNKNOWN
    compact = re.sub(r"\s+", "", raw)
    if compact in ("审3", "表3"):
        return RollforwardPeriodRole.ENDING
    if compact in ("审2", "表2"):
        return RollforwardPeriodRole.OPENING
    if "checkwith" in compact.replace(" ", "").lower():
        return RollforwardPeriodRole.UNKNOWN
    if "审3" in raw or raw.startswith("表3"):
        return RollforwardPeriodRole.ENDING
    if "审2" in raw or raw.startswith("表2"):
        return RollforwardPeriodRole.OPENING
    if "期初" in raw or "年初" in raw or "上年" in raw:
        return RollforwardPeriodRole.OPENING
    if "期末" in raw or "年末" in raw or raw.startswith("本年"):
        return RollforwardPeriodRole.ENDING
    return RollforwardPeriodRole.UNKNOWN


def _apply_dual_period_column_roles(
    rows: list[tuple[Any, ...]],
    header_row: int | None,
    bindings: list[RollforwardColumnBinding],
) -> list[RollforwardColumnBinding]:
    """将 header 上方审2/审3 等块标签继承到金额列 binding。"""
    if not header_row or header_row < 3 or not bindings:
        return bindings
    anchors: list[tuple[int, RollforwardPeriodRole]] = []
    base_idx = header_row - 1
    for delta in range(2, 6):
        ri = base_idx - delta
        if ri < 0 or ri >= len(rows):
            continue
        row = rows[ri]
        for col_i, val in enumerate(row):
            role = _period_role_from_block_label(str(val) if val is not None else "")
            if role != RollforwardPeriodRole.UNKNOWN:
                anchors.append((col_i + 1, role))
    if not anchors:
        return bindings
    anchors.sort(key=lambda x: x[0])
    out: list[RollforwardColumnBinding] = []
    for b in bindings:
        role = b.period_role
        if role == RollforwardPeriodRole.UNKNOWN:
            inherited = RollforwardPeriodRole.UNKNOWN
            for col, r in anchors:
                if col <= b.column_index:
                    inherited = r
            role = inherited
        out.append(
            RollforwardColumnBinding(
                measure=b.measure,
                period_role=role,
                column_index=b.column_index,
                source_header=b.source_header,
            )
        )
    return out


def _supplement_movement_bindings(
    rows: list[tuple[Any, ...]],
    bindings: list[RollforwardColumnBinding],
) -> list[RollforwardColumnBinding]:
    """扫描「原值变动金额」等行，补充 movement 列绑定。"""
    seen = {b.column_index for b in bindings}
    out = list(bindings)
    for row in rows:
        for col_i, val in enumerate(row):
            raw = _cell_str(val)
            if not raw or "变动" not in raw:
                continue
            measure = _infer_rollforward_measure(raw)
            if measure is None:
                continue
            col = col_i + 1
            if col in seen:
                for i, b in enumerate(out):
                    if b.column_index == col and b.period_role == RollforwardPeriodRole.UNKNOWN:
                        out[i] = RollforwardColumnBinding(
                            measure=b.measure,
                            period_role=RollforwardPeriodRole.MOVEMENT,
                            column_index=b.column_index,
                            source_header=b.source_header,
                        )
                continue
            seen.add(col)
            out.append(
                RollforwardColumnBinding(
                    measure=measure,
                    period_role=RollforwardPeriodRole.MOVEMENT,
                    column_index=col,
                    source_header=raw,
                )
            )
    return out


def _detect_movement_rows(rows: list[tuple[Any, ...]]) -> bool:
    movement_row_tokens = (
        "原值变动金额",
        "累计折旧变动金额",
        "减值准备变动金额",
        "净值变动金额",
        "处置或报废",
    )
    transaction_row_tokens = ("购置", "计提折旧", "计提", "在建工程转入")
    for row in rows:
        for val in row[:6]:
            text = _cell_str(val)
            if not text:
                continue
            if any(tok in text for tok in movement_row_tokens):
                return True
            if text in transaction_row_tokens:
                return True
            if text == "变动":
                return True
    return False


def _sheet_text_blob(rows: list[tuple[Any, ...]], *, max_rows: int = 80) -> str:
    parts: list[str] = []
    for row in rows[:max_rows]:
        for val in row[:30]:
            text = _cell_str(val)
            if text:
                parts.append(text)
    return " ".join(parts)


def _detect_k01_sections(
    rows: list[tuple[Any, ...]],
    *,
    has_movement_rows: bool,
) -> tuple[dict[str, bool], dict[str, list[str]]]:
    """识别 K.01 六区块（presence + 证据锚点）。"""
    blob = _sheet_text_blob(rows, max_rows=140)
    short_labels = {
        _cell_str(v)
        for row in rows[:140]
        for v in row[:30]
        if _cell_str(v) and len(_cell_str(v) or "") <= 24
    }

    def _contains_any(tokens: tuple[str, ...]) -> list[str]:
        hits = [t for t in tokens if t in blob]
        return hits[:4]

    evidence: dict[str, list[str]] = {}
    presence: dict[str, bool] = {}

    # 区块 1：表1 BKD 主矩阵
    b1_hits = _contains_any(("表1", "固定资产类别", "年初余额", "年末余额", "账面数", "审定数"))
    presence["b1_bkd_main_table"] = ("固定资产类别" in blob) and (
        ("表1" in blob) or ("年初余额" in blob and "年末余额" in blob)
    )
    evidence["b1_bkd_main_table"] = b1_hits

    # 区块 2：变动/TB 勾稽区
    b2_hits = _contains_any(
        ("原值变动金额", "累计折旧变动金额", "减值准备变动金额", "TB-原值", "TB-累计折旧", "差异")
    )
    presence["b2_movement_tb_reconciliation"] = has_movement_rows or any(
        token.startswith("TB-") or "变动金额" in token for token in b2_hits
    )
    evidence["b2_movement_tb_reconciliation"] = b2_hits

    # 区块 3：表2（FA list 分类汇总）
    b3_hits = _contains_any(("表2", "固定资产清单", "分类汇总", "表2 check with 表1"))
    presence["b3_table2_fa_summary"] = ("表2" in short_labels) or ("固定资产清单" in blob and "表2" in blob)
    evidence["b3_table2_fa_summary"] = b3_hits

    # 区块 4：表3（表2 与表1 对勾）
    b4_hits = _contains_any(("表3", "表2 check with 表1", "check with", "核对一致"))
    presence["b4_table3_check_with_table1"] = ("表3" in short_labels) or ("表2 check with 表1" in blob)
    evidence["b4_table3_check_with_table1"] = b4_hits

    # 区块 5：表4（折旧费用与利润表核对）
    b5_hits = _contains_any(("表4", "折旧费用与利润表科目核对", "利润表金额", "折旧费用"))
    presence["b5_table4_depreciation_pl"] = ("表4" in short_labels) or (
        "折旧费用" in blob and ("利润表" in blob or "试算表" in blob)
    )
    evidence["b5_table4_depreciation_pl"] = b5_hits

    # 区块 6：Notes / 差异调查 / 程序路由（TE）
    b6_hits = _contains_any(("Notes", "SAD", "TE", "K.02", "K.03", "拒绝", "不执行的原因", "调查"))
    presence["b6_notes_investigation_routing"] = bool(b6_hits)
    evidence["b6_notes_investigation_routing"] = b6_hits

    return presence, evidence


def _anchor_hits_in_row(row: tuple[Any, ...], section_id: str) -> list[str]:
    """单行内命中某区块的锚点词（用于定位行号）。"""
    hits: list[str] = []
    cells = [_cell_str(v) for v in row[:24]]
    texts = [t for t in cells if t]

    def _short_label(t: str, max_len: int = 12) -> bool:
        return len(t) <= max_len

    if section_id == "b1_bkd_main_table":
        for t in texts:
            if t == "表1" or (t.startswith("表1") and len(t) <= 4):
                hits.append("表1")
            if "固定资产类别" in t and _short_label(t, 20):
                hits.append("固定资产类别")
            if t in ("年初余额", "年末余额", "账面数", "审定数"):
                hits.append(t)
    elif section_id == "b2_movement_tb_reconciliation":
        row_blob = " ".join(texts)
        has_tb_context = "TB" in row_blob or "试算表" in row_blob or "变动金额" in row_blob
        for t in texts:
            if "原值变动金额" in t or "累计折旧变动金额" in t:
                hits.append(t)
            if t.startswith("TB-"):
                hits.append(t)
            if t == "变动" or (t == "差异" and has_tb_context):
                hits.append(t)
    elif section_id == "b3_table2_fa_summary":
        for t in texts:
            if t == "表2":
                hits.append("表2")
            if "固定资产清单" in t:
                hits.append("固定资产清单")
    elif section_id == "b4_table3_check_with_table1":
        for t in texts:
            if t == "表3":
                hits.append("表3")
            if "表2 check with 表1" in t:
                hits.append("表2 check with 表1")
    elif section_id == "b5_table4_depreciation_pl":
        for t in texts:
            if t == "表4":
                hits.append("表4")
            if "折旧费用与利润表" in t:
                hits.append(t)
    elif section_id == "b6_notes_investigation_routing":
        for t in texts:
            if t == "Notes" or t.startswith("Notes"):
                hits.append("Notes")
            if t in ("SAD", "TE") or "调查" in t:
                hits.append(t)
    return hits[:4]


def _locate_section_anchor_rows(rows: list[tuple[Any, ...]]) -> dict[str, list[int]]:
    """各区块首次命中锚点的行号（1-based），同区块可出现多次。"""
    found: dict[str, list[int]] = {sid: [] for sid in K01_SECTION_IDS}
    for r_idx, row in enumerate(rows):
        if row is None:
            continue
        row_no = r_idx + 1
        for sid in K01_SECTION_IDS:
            if _anchor_hits_in_row(row, sid):
                found[sid].append(row_no)
    return found


def _build_section_regions(
    rows: list[tuple[Any, ...]],
    anchor_rows: dict[str, list[int]],
) -> dict[str, K01SectionRegion]:
    """按锚点行序切分各区块起止行（未命中锚点则无行范围）。"""
    ordered: list[tuple[int, str, str]] = []
    for sid in K01_SECTION_IDS:
        for row_no in anchor_rows.get(sid, []):
            ordered.append((row_no, sid, ""))
    ordered.sort(key=lambda x: x[0])
    if not ordered:
        return {}

    row_count = len(rows)
    # 去重：同一行只保留最先出现的 section（避免一行多标签）
    seen_rows: set[int] = set()
    unique_ordered: list[tuple[int, str]] = []
    for row_no, sid, _ in ordered:
        if row_no in seen_rows:
            continue
        seen_rows.add(row_no)
        unique_ordered.append((row_no, sid))

    first_by_section: list[tuple[int, str]] = []
    previous_anchor = 0
    for sid in K01_SECTION_IDS:
        candidates = sorted(row_no for row_no in anchor_rows.get(sid, []) if row_no > previous_anchor)
        if not candidates:
            continue
        anchor_row = candidates[0]
        first_by_section.append((anchor_row, sid))
        previous_anchor = anchor_row

    regions: dict[str, K01SectionRegion] = {}
    for i, (anchor_row, sid) in enumerate(first_by_section):
        end_row = first_by_section[i + 1][0] - 1 if i + 1 < len(first_by_section) else row_count
        hits = _anchor_hits_in_row(rows[anchor_row - 1], sid) if anchor_row <= len(rows) else []
        regions[sid] = K01SectionRegion(
            section_id=sid,
            anchor_row=anchor_row,
            start_row=anchor_row,
            end_row=max(anchor_row, end_row),
            evidence=hits,
        )
    return regions


def _detect_section_conflicts(
    rows: list[tuple[Any, ...]],
    *,
    anchor_rows: dict[str, list[int]],
    regions: dict[str, K01SectionRegion],
    header_row: int | None,
    col_by_field: dict[str, int],
    bindings: list[RollforwardColumnBinding],
) -> list[str]:
    conflicts: list[str] = []

    for sid, rows_hit in anchor_rows.items():
        if len(rows_hit) > 1:
            conflicts.append(f"duplicate_anchor:{sid}:rows={rows_hit[:5]}")

    b3_row = anchor_rows.get("b3_table2_fa_summary", [None])[0] if anchor_rows.get("b3_table2_fa_summary") else None
    b4_row = anchor_rows.get("b4_table3_check_with_table1", [None])[0] if anchor_rows.get(
        "b4_table3_check_with_table1"
    ) else None
    if b3_row is not None and b4_row is not None and b4_row < b3_row:
        conflicts.append("anchor_order:table3_before_table2")

    b1 = regions.get("b1_bkd_main_table")
    if b1 and b1.start_row and b1.end_row:
        total_hits = 0
        for r_idx in range(b1.start_row - 1, min(b1.end_row, len(rows))):
            row = rows[r_idx]
            if row is None:
                continue
            if not _row_has_total_label(row):
                continue
            if _row_plausible_total(row, col_by_field, bindings):
                total_hits += 1
        if total_hits > 1:
            conflicts.append(f"ambiguous_total_rows_in_b1:count={total_hits}")

    # 同一标准列号在多个区块表头行被赋予不同 measure
    measure_by_col: dict[int, set[str]] = {}
    for sid, region in regions.items():
        if not region.start_row or not region.end_row:
            continue
        for r_idx in range(region.start_row - 1, min(region.end_row, len(rows))):
            row = rows[r_idx]
            if row is None:
                continue
            for col_i, val in enumerate(row[:30]):
                raw = _cell_str(val)
                if not raw:
                    continue
                measure = _infer_rollforward_measure(raw)
                if measure is None:
                    continue
                col = col_i + 1
                measure_by_col.setdefault(col, set()).add(f"{sid}:{measure}")
    for col, tags in measure_by_col.items():
        measures = {t.split(":", 1)[1] for t in tags}
        if len(measures) > 1:
            conflicts.append(f"duplicate_column_semantics:col{col}={sorted(measures)}")

    if header_row and b1 and b1.start_row and b1.end_row:
        if header_row < b1.start_row or header_row > b1.end_row:
            conflicts.append("header_outside_b1_region")

    return conflicts


def _compute_recognition_confidence(
    *,
    section_presence: dict[str, bool],
    section_conflicts: list[str],
    layout_profile: RollforwardLayoutProfile,
) -> float:
    score = 0.2
    if layout_profile != RollforwardLayoutProfile.UNRECOGNIZED:
        score += 0.15
    present = sum(1 for ok in section_presence.values() if ok)
    score += min(0.45, present * 0.075)
    score -= min(0.4, len(section_conflicts) * 0.08)
    return round(max(0.0, min(1.0, score)), 3)


def _numeric_values_in_region(
    rows: list[tuple[Any, ...]],
    region: K01SectionRegion | None,
    *,
    max_cols: int = 30,
) -> list[tuple[int, Decimal]]:
    if region is None or not region.start_row or not region.end_row:
        return []

    values: list[tuple[int, Decimal]] = []
    for r_idx in range(region.start_row - 1, min(region.end_row, len(rows))):
        row = rows[r_idx]
        if row is None:
            continue
        for val in row[:max_cols]:
            amt = parse_amount(_cell_str(val))
            if amt is not None:
                values.append((r_idx + 1, amt))
    return values


def _extract_side_by_side_table2_table3(
    rows: list[tuple[Any, ...]],
) -> tuple[int, list[Decimal], int | None]:
    """读取表2/表3横向并排的模板。

    常见版式：同一行左侧为“表2”，右侧为“表3”；下方左侧是 FA list
    分类汇总金额，右侧是“表2 check with 表1”差异列。
    """
    for r_idx, row in enumerate(rows):
        table2_col: int | None = None
        table3_col: int | None = None
        for c_idx, val in enumerate(row[:40]):
            text = _cell_str(val)
            if text == "表2":
                table2_col = c_idx + 1
            elif text == "表3":
                table3_col = c_idx + 1
        if table2_col is None or table3_col is None or table3_col <= table2_col:
            continue

        start = r_idx + 1
        end = min(len(rows), start + 20)
        table2_values: list[Decimal] = []
        table3_values_by_row: list[tuple[int, Decimal]] = []
        total_row_values: list[tuple[int, Decimal]] = []
        for rr in range(start, end):
            data = rows[rr]
            if data is None:
                continue
            row_no = rr + 1
            for c in range(table2_col + 1, table3_col - 1):
                amt = _amount_at_col(data, c)
                if amt is not None:
                    table2_values.append(amt)
            row_table3_values: list[Decimal] = []
            for c in range(table3_col, min(table3_col + 4, len(data)) + 1):
                amt = _amount_at_col(data, c)
                if amt is not None:
                    row_table3_values.append(amt)
            for amt in row_table3_values:
                table3_values_by_row.append((row_no, amt))
            if row_table3_values and _row_has_total_label(data):
                total_row_values.extend((row_no, amt) for amt in row_table3_values)

        chosen = total_row_values or table3_values_by_row
        return len(table2_values), [v for _, v in chosen], chosen[0][0] if chosen else None

    return 0, [], None


def _text_cells_in_region(
    rows: list[tuple[Any, ...]],
    region: K01SectionRegion | None,
    *,
    max_cols: int = 30,
) -> list[tuple[int, int, str]]:
    if region is None or not region.start_row or not region.end_row:
        return []

    cells: list[tuple[int, int, str]] = []
    for r_idx in range(region.start_row - 1, min(region.end_row, len(rows))):
        row = rows[r_idx]
        if row is None:
            continue
        for c_idx, val in enumerate(row[:max_cols]):
            text = _cell_str(val)
            if text:
                cells.append((r_idx + 1, c_idx + 1, text))
    return cells


def _extract_tb_check(
    rows: list[tuple[Any, ...]],
    *,
    tb_region: K01SectionRegion | None,
    notes_region: K01SectionRegion | None,
) -> tuple[bool, float, list[Decimal], int | None, bool, int | None, str | None]:
    """读取 K.01 区块2的 TB 核对信息。

    可靠识别必须看到 TB 相关字样和差异字段；仅有“变动金额”不视为已完成 TB check。
    """
    tb_cells = _text_cells_in_region(rows, tb_region)
    tb_hits = [
        t
        for _, _, t in tb_cells
        if t.startswith("TB-") or "试算表" in t or t.upper() == "TB"
    ]
    diff_cells = [(r, c, t) for r, c, t in tb_cells if "差异" in t]
    diff_cols = {c for _, c, t in diff_cells if len(t) <= 20}
    diff_rows = {r for r, _, _ in diff_cells}

    diff_values: list[tuple[int, Decimal]] = []
    if tb_region and tb_region.start_row and tb_region.end_row:
        for r_idx in range(tb_region.start_row - 1, min(tb_region.end_row, len(rows))):
            row = rows[r_idx]
            if row is None:
                continue
            row_no = r_idx + 1
            row_has_diff_label = row_no in diff_rows
            for c_idx, val in enumerate(row[:30]):
                col_no = c_idx + 1
                if not row_has_diff_label and col_no not in diff_cols:
                    continue
                amt = parse_amount(_cell_str(val))
                if amt is not None:
                    diff_values.append((row_no, amt))

    confidence = 0.0
    if tb_region is not None:
        confidence += 0.1
    if tb_hits:
        confidence += 0.45
    if diff_cells:
        confidence += 0.35
    if diff_values:
        confidence += 0.1
    confidence = round(min(confidence, 1.0), 3)
    detected = bool(tb_hits and diff_cells and confidence >= 0.65)

    notes_cells = _text_cells_in_region(rows, notes_region)
    note_parts: list[str] = []
    notes_row: int | None = None
    for row_no, _, text in notes_cells:
        norm = re.sub(r"\s+", "", text).lower()
        if norm in ("notes", "sad", "te") or text in ("Notes", "SAD", "TE"):
            continue
        if "超过SAD差异调查" in text or "超过TE" in text or "拒绝执行原因" in text:
            continue
        if parse_amount(text) is not None:
            continue
        if len(text) >= 4:
            note_parts.append(text)
            notes_row = notes_row or row_no
    notes_text = "\n".join(note_parts).strip() if note_parts else None
    return (
        detected,
        confidence,
        [v for _, v in diff_values],
        diff_values[0][0] if diff_values else None,
        bool(notes_text),
        notes_row,
        notes_text,
    )


def _extract_note_text(
    rows: list[tuple[Any, ...]],
    region: K01SectionRegion | None,
    *,
    max_cols: int = 30,
) -> tuple[bool, int | None, str | None]:
    notes_cells = _text_cells_in_region(rows, region, max_cols=max_cols)
    note_parts: list[str] = []
    notes_row: int | None = None
    for row_no, _, text in notes_cells:
        norm = re.sub(r"\s+", "", text).lower()
        if norm in ("notes", "sad", "te") or text in ("Notes", "SAD", "TE"):
            continue
        if "超过SAD差异调查" in text or "超过TE" in text or "拒绝执行原因" in text:
            continue
        if parse_amount(text) is not None:
            continue
        if len(text) >= 4:
            note_parts.append(text)
            notes_row = notes_row or row_no
    notes_text = "\n".join(note_parts).strip() if note_parts else None
    return bool(notes_text), notes_row, notes_text


def _extract_table4_depreciation_check(
    rows: list[tuple[Any, ...]],
    *,
    table4_region: K01SectionRegion | None,
    notes_region: K01SectionRegion | None,
) -> tuple[
    list[Decimal],
    Decimal | None,
    int | None,
    Decimal | None,
    int | None,
    Decimal | None,
    int | None,
    bool,
    int | None,
    str | None,
]:
    if table4_region is None or not table4_region.start_row or not table4_region.end_row:
        table4_region = _infer_table4_region(rows, notes_region=notes_region)
    if table4_region is None or not table4_region.start_row or not table4_region.end_row:
        return [], None, None, None, None, None, None, False, None, None

    table4_end_row = table4_region.end_row
    if notes_region and notes_region.start_row and notes_region.start_row > table4_region.start_row:
        table4_end_row = max(table4_end_row, notes_region.start_row - 1)

    amount_col: int | None = None
    header_row: int | None = None
    for r_idx in range(table4_region.start_row - 1, min(table4_end_row, len(rows))):
        row = rows[r_idx]
        for c_idx, val in enumerate(row[:30]):
            text = _cell_str(val)
            if text == "金额":
                amount_col = c_idx + 1
                header_row = r_idx + 1
                break
        if amount_col:
            break

    def row_texts(row: tuple[Any, ...]) -> list[str]:
        return [_cell_str(v) or "" for v in row[:30]]

    def amount_in_row(row: tuple[Any, ...]) -> Decimal | None:
        if amount_col is not None:
            return _amount_at_col(row, amount_col)
        values = [parse_amount(_cell_str(v)) for v in row[:30]]
        parsed = [v for v in values if v is not None]
        return parsed[-1] if parsed else None

    pl_amounts: list[Decimal] = []
    pl_total: Decimal | None = None
    pl_total_row: int | None = None
    depreciation_amount: Decimal | None = None
    depreciation_row: int | None = None
    difference: Decimal | None = None
    difference_row: int | None = None

    for r_idx in range(table4_region.start_row - 1, min(table4_end_row, len(rows))):
        row = rows[r_idx]
        row_no = r_idx + 1
        texts = row_texts(row)
        joined = " ".join(t for t in texts if t)
        amt = amount_in_row(row)
        if "差异" in texts:
            difference = amt
            difference_row = row_no
            continue
        if "合计" in texts:
            pl_total = amt
            pl_total_row = row_no
            continue
        if "累计折旧科目-本年计提" in joined or ("TB" in texts and "累计折旧" in joined):
            depreciation_amount = amt
            depreciation_row = row_no
            continue
        if header_row is not None and row_no > header_row and pl_total_row is None and amt is not None:
            pl_amounts.append(amt)

    notes_present, notes_row, notes_text = _extract_note_text(rows, notes_region)
    return (
        pl_amounts,
        pl_total,
        pl_total_row,
        depreciation_amount,
        depreciation_row,
        difference,
        difference_row,
        notes_present,
        notes_row,
        notes_text,
    )


def _infer_table4_region(
    rows: list[tuple[Any, ...]],
    *,
    notes_region: K01SectionRegion | None,
) -> K01SectionRegion | None:
    start_row: int | None = None
    evidence: list[str] = []
    for r_idx, row in enumerate(rows):
        texts = [_cell_str(v) or "" for v in row[:30]]
        joined = " ".join(t for t in texts if t)
        if "折旧费用与利润表科目核对" in joined:
            start_row = r_idx + 1
            evidence.append("折旧费用与利润表科目核对")
            break
        if "科目名称" in texts and "金额" in texts:
            start_row = r_idx + 1
            evidence.append("科目名称/金额")
            break
        if "累计折旧科目-本年计提" in joined:
            start_row = max(1, r_idx - 6)
            evidence.append("累计折旧科目-本年计提")
            break
    if start_row is None:
        return None

    end_row = len(rows)
    if notes_region and notes_region.start_row and notes_region.start_row > start_row:
        end_row = notes_region.start_row - 1
    else:
        for r_idx in range(start_row, len(rows)):
            texts = [_cell_str(v) or "" for v in rows[r_idx][:8]]
            if any(t == "Notes" or t.startswith("Notes") for t in texts if t):
                end_row = r_idx
                break

    return K01SectionRegion(
        section_id="b5_table4_depreciation_pl",
        anchor_row=start_row,
        start_row=start_row,
        end_row=max(start_row, end_row),
        evidence=evidence,
    )


def _presence_from_regions(regions: dict[str, K01SectionRegion]) -> dict[str, bool]:
    return {sid: sid in regions for sid in K01_SECTION_IDS}


def _merge_section_presence(
    blob_presence: dict[str, bool],
    regions: dict[str, K01SectionRegion],
) -> dict[str, bool]:
    """行锚点优先：有 region 则视为 presence；否则保留全文扫描结果。"""
    out = dict(blob_presence)
    for sid in K01_SECTION_IDS:
        if sid in regions:
            out[sid] = True
    return out


def _col_by_field_in_row_range(
    rows: list[tuple[Any, ...]],
    *,
    start_row: int,
    end_row: int,
) -> dict[str, int]:
    """仅在区块行范围内扫描表头，避免插入表同名列污染列绑定。"""
    if start_row < 1 or end_row < start_row:
        return {}
    sub = rows[start_row - 1 : end_row]
    _, header_cells, _ = scan_rows_for_headers(sub, sheet_kind=SheetKind.ROLLFORWARD)
    if not header_cells:
        return {}
    mapped, _ = map_headers(header_cells, sheet_kind=SheetKind.ROLLFORWARD)
    return {m.standard_field: m.column_index for m in mapped}


def _find_total_row_in_range(
    rows: list[tuple[Any, ...]],
    *,
    start_row: int,
    end_row: int,
    col_by_field: dict[str, int],
    bindings: list[RollforwardColumnBinding],
) -> tuple[int | None, tuple[Any, ...] | None]:
    for r_idx in range(max(0, start_row - 1), min(end_row, len(rows))):
        row = rows[r_idx]
        if row is None or not _row_has_total_label(row):
            continue
        if not _row_plausible_total(row, col_by_field, bindings):
            continue
        return r_idx + 1, row
    return None, None


def _detect_layout_profile(
    rows: list[tuple[Any, ...]],
    bindings: list[RollforwardColumnBinding],
    *,
    has_movement_rows: bool,
) -> RollforwardLayoutProfile:
    blob = _sheet_text_blob(rows)
    short_labels = {
        _cell_str(v)
        for row in rows[:70]
        for v in row[:20]
        if _cell_str(v) and len(_cell_str(v) or "") <= 8
    }
    if {"表2", "表3"}.issubset(short_labels) or {"审2", "审3"}.issubset(short_labels):
        if has_movement_rows:
            return RollforwardLayoutProfile.HYBRID
        return RollforwardLayoutProfile.CATEGORY_DUAL_PERIOD
    if (
        "账面数" in blob
        and "账表调整" in blob
        and "固定资产类别" in blob
        and re.search(r"(?:^|\s)表1(?:\s|$)", blob)
    ):
        return RollforwardLayoutProfile.SOP_BKD_MATRIX
    has_period = any(
        b.period_role in (RollforwardPeriodRole.OPENING, RollforwardPeriodRole.ENDING)
        for b in bindings
    )
    if has_movement_rows and ("固定资产类别" in blob or "审2" in blob or "TB-" in blob):
        return RollforwardLayoutProfile.HYBRID
    if has_period or "固定资产类别" in blob or "审2" in blob:
        return RollforwardLayoutProfile.CATEGORY_DUAL_PERIOD
    if bindings or "后推" in blob or "Agree" in blob:
        return RollforwardLayoutProfile.CATEGORY_DUAL_PERIOD
    return RollforwardLayoutProfile.UNRECOGNIZED


def _choose_rollforward_candidate(candidates: list[SheetLoadCandidate]) -> SheetLoadCandidate:
    """多 K.01 候选时优先当年主表（降低 -24 / 尾随 - 权重）。"""

    def sort_key(c: SheetLoadCandidate) -> tuple[float, float, str]:
        name = c.sheet_name.strip()
        penalty = 0.0
        if re.search(r"-24\s*$", name, re.I):
            penalty += 1.0
        if name.endswith("-") and not name.lower().endswith("gl"):
            penalty += 0.5
        return (penalty, -c.confidence, name)

    return sorted(candidates, key=sort_key)[0]


def infer_rollforward_column_bindings(
    header_cells: list[tuple[int, str]],
) -> list[RollforwardColumnBinding]:
    """根据表头文本推断后推表金额列的口径与期初/变动/期末角色。"""
    out: list[RollforwardColumnBinding] = []
    seen_cols: set[int] = set()
    for col_idx, text in header_cells:
        raw = str(text).strip()
        measure = _infer_rollforward_measure(raw)
        if measure is None:
            continue
        if col_idx in seen_cols:
            continue
        seen_cols.add(col_idx)
        role = _infer_rollforward_period_role(raw)
        out.append(
            RollforwardColumnBinding(
                measure=measure,
                period_role=role,
                column_index=col_idx,
                source_header=raw,
            )
        )
    return out


def _extract_totals_from_bindings(
    row: tuple[Any, ...],
    bindings: list[RollforwardColumnBinding],
    role: RollforwardPeriodRole,
) -> dict[str, Decimal | None]:
    totals: dict[str, Decimal | None] = {}
    for measure in ("original_value", "accumulated_depreciation", "impairment_provision", "net_value"):
        cols = sorted({b.column_index for b in bindings if b.measure == measure and b.period_role == role})
        val: Decimal | None = None
        for c in cols:
            v = _amount_at_col(row, c)
            if v is not None:
                val = v
                break
        totals[measure] = val
    return totals


def _binding_totals_have_values(totals: dict[str, Decimal | None]) -> bool:
    return any(v is not None for v in totals.values())


def _totals_all_zero(totals: dict[str, Decimal | None]) -> bool:
    vals = [v for v in totals.values() if v is not None]
    return bool(vals) and all(v == 0 for v in vals)


def _row_plausible_total(
    row: tuple[Any, ...],
    col_by_field: dict[str, int],
    bindings: list[RollforwardColumnBinding],
) -> bool:
    if col_by_field:
        c = _extract_totals_from_row(row, col_by_field)
        if any(v is not None for v in c.values()):
            return True
    if bindings:
        for role in (
            RollforwardPeriodRole.ENDING,
            RollforwardPeriodRole.UNKNOWN,
            RollforwardPeriodRole.OPENING,
        ):
            c = _extract_totals_from_bindings(row, bindings, role)
            if _binding_totals_have_values(c):
                return True
    return False


def parse_rollforward_rows(
    rows: list[tuple[Any, ...]],
    *,
    source_file: str = "",
    source_sheet: str = "",
) -> RollforwardSheetDataset:
    fa_parsed = parse_fa_list_rows(
        rows,
        source_file=source_file,
        source_sheet=source_sheet,
        sheet_kind=SheetKind.ROLLFORWARD,
    )
    header_row, header_cells, _ = scan_rows_for_headers(rows, sheet_kind=SheetKind.ROLLFORWARD)
    mapped_fields, _ = map_headers(header_cells, sheet_kind=SheetKind.ROLLFORWARD) if header_cells else ([], [])
    col_by_field = {m.standard_field: m.column_index for m in mapped_fields}
    bindings = infer_rollforward_column_bindings(header_cells) if header_cells else []
    bindings = _apply_dual_period_column_roles(rows, header_row, bindings)
    bindings = _supplement_movement_bindings(rows, bindings)
    has_movement_rows = _detect_movement_rows(rows)
    layout_profile = _detect_layout_profile(rows, bindings, has_movement_rows=has_movement_rows)
    blob_presence, section_evidence = _detect_k01_sections(rows, has_movement_rows=has_movement_rows)
    anchor_rows = _locate_section_anchor_rows(rows)
    section_regions = _build_section_regions(rows, anchor_rows)
    section_presence = _merge_section_presence(blob_presence, section_regions)
    section_conflicts = _detect_section_conflicts(
        rows,
        anchor_rows=anchor_rows,
        regions=section_regions,
        header_row=header_row,
        col_by_field=col_by_field,
        bindings=bindings,
    )
    recognition_confidence = _compute_recognition_confidence(
        section_presence=section_presence,
        section_conflicts=section_conflicts,
        layout_profile=layout_profile,
    )

    ending: dict[str, Decimal | None] = {}
    opening: dict[str, Decimal | None] = {}
    total_row: int | None = None
    notes: list[str] = []
    if section_presence:
        present_cnt = sum(1 for ok in section_presence.values() if ok)
        notes.append(f"k01_sections_detected:{present_cnt}/6")
    if section_regions:
        notes.append(f"k01_section_regions:{len(section_regions)}")
    if section_conflicts:
        notes.append("k01_section_conflicts")
    if recognition_confidence < 0.65:
        notes.append("k01_recognition_needs_review")
    table2_values = _numeric_values_in_region(
        rows,
        section_regions.get("b3_table2_fa_summary"),
    )
    table3_values_with_rows = _numeric_values_in_region(
        rows,
        section_regions.get("b4_table3_check_with_table1"),
    )
    table2_amount_count = len(table2_values)
    table3_check_values = [v for _, v in table3_values_with_rows]
    table3_check_row = table3_values_with_rows[0][0] if table3_values_with_rows else None
    side_table2_count, side_table3_values, side_table3_row = _extract_side_by_side_table2_table3(rows)
    if side_table2_count:
        table2_amount_count = max(table2_amount_count, side_table2_count)
        notes.append("k01_table2_side_by_side_amounts")
    if side_table3_values:
        table3_check_values = side_table3_values
        table3_check_row = side_table3_row
        notes.append("k01_table3_side_by_side_check_values")
    if table2_amount_count:
        notes.append(f"k01_table2_amounts:{table2_amount_count}")
    if table3_check_values:
        notes.append(f"k01_table3_check_values:{len(table3_check_values)}")
    (
        tb_reconciliation_detected,
        tb_reconciliation_confidence,
        tb_difference_values,
        tb_difference_row,
        tb_notes_text_present,
        tb_notes_row,
        tb_notes_text,
    ) = _extract_tb_check(
        rows,
        tb_region=section_regions.get("b2_movement_tb_reconciliation"),
        notes_region=section_regions.get("b6_notes_investigation_routing"),
    )
    if tb_reconciliation_detected:
        notes.append(f"k01_tb_check_confidence:{tb_reconciliation_confidence}")
    elif section_presence.get("b2_movement_tb_reconciliation"):
        notes.append(f"k01_tb_check_needs_review:{tb_reconciliation_confidence}")
    (
        table4_pl_amounts,
        table4_pl_total,
        table4_pl_total_row,
        table4_rollforward_depreciation,
        table4_rollforward_depreciation_row,
        table4_difference,
        table4_difference_row,
        table4_notes_text_present,
        table4_notes_row,
        table4_notes_text,
    ) = _extract_table4_depreciation_check(
        rows,
        table4_region=section_regions.get("b5_table4_depreciation_pl"),
        notes_region=section_regions.get("b6_notes_investigation_routing"),
    )
    if table4_pl_total is not None or table4_difference is not None:
        notes.append("k01_table4_depreciation_check_values")
    if any(
        b.period_role in (RollforwardPeriodRole.OPENING, RollforwardPeriodRole.ENDING)
        for b in bindings
    ):
        notes.append("period_labels_applied")
    total_row_data: tuple[Any, ...] | None = None

    b1_region = section_regions.get("b1_bkd_main_table")
    col_for_totals = col_by_field
    if b1_region and b1_region.start_row and b1_region.end_row:
        scoped = _col_by_field_in_row_range(
            rows,
            start_row=b1_region.start_row,
            end_row=b1_region.end_row,
        )
        if scoped:
            col_for_totals = scoped
            notes.append("totals_columns_from_b1_region")
    if b1_region and b1_region.start_row and b1_region.end_row and (col_for_totals or bindings):
        total_row, total_row_data = _find_total_row_in_range(
            rows,
            start_row=b1_region.start_row,
            end_row=b1_region.end_row,
            col_by_field=col_for_totals,
            bindings=bindings,
        )

    if total_row_data is None and header_row and (col_for_totals or bindings):
        start = header_row
        for r_idx in range(start, len(rows)):
            row = rows[r_idx]
            if row is None or not _row_has_total_label(row):
                continue
            if not _row_plausible_total(row, col_for_totals, bindings):
                continue
            total_row_data = row
            total_row = r_idx + 1
            break

    if total_row_data is not None:
        has_period_bindings = any(
            b.period_role in (RollforwardPeriodRole.OPENING, RollforwardPeriodRole.ENDING) for b in bindings
        )
        if has_period_bindings:
            opening = _extract_totals_from_bindings(
                total_row_data, bindings, RollforwardPeriodRole.OPENING
            )
            ending = _extract_totals_from_bindings(
                total_row_data, bindings, RollforwardPeriodRole.ENDING
            )
            if not _binding_totals_have_values(ending):
                unk = _extract_totals_from_bindings(
                    total_row_data, bindings, RollforwardPeriodRole.UNKNOWN
                )
                if _binding_totals_have_values(unk):
                    ending = unk
                elif col_for_totals:
                    ending = _extract_totals_from_row(total_row_data, col_for_totals)
            notes.append("totals_from_period_bindings")
        elif col_for_totals:
            ending = _extract_totals_from_row(total_row_data, col_for_totals)
            notes.append("ending_from_total_row")
        elif bindings:
            ending = _extract_totals_from_bindings(
                total_row_data, bindings, RollforwardPeriodRole.UNKNOWN
            )
            if _binding_totals_have_values(ending):
                notes.append("ending_from_total_row_unknown_binding")

    if (
        side_table3_values
        and _binding_totals_have_values(opening)
        and _totals_all_zero(ending)
    ):
        ending = dict(opening)
        opening = {}
        notes.append("ending_from_left_table_when_right_side_is_check")

    if not _binding_totals_have_values(ending):
        detail = [
            r
            for r in fa_parsed.records
            if any(
                parse_amount(getattr(r, f, None)) is not None
                for f in ("original_value", "accumulated_depreciation", "net_value")
            )
        ]
        if detail:
            ending = {
                "original_value": _sum_records(detail, "original_value"),
                "accumulated_depreciation": _sum_records(detail, "accumulated_depreciation"),
                "impairment_provision": _sum_records(detail, "impairment_provision"),
                "net_value": _sum_records(detail, "net_value"),
            }
            notes.append("ending_from_detail_sum")

    return RollforwardSheetDataset(
        source_file=source_file,
        source_sheet=source_sheet,
        header_row=header_row,
        mapped_fields=fa_parsed.mapped_fields or mapped_fields,
        amount_column_bindings=bindings,
        detail_records=fa_parsed.records,
        opening_totals=opening,
        ending_totals=ending,
        total_row=total_row,
        layout_profile=layout_profile,
        has_movement_rows=has_movement_rows,
        section_presence=section_presence,
        section_evidence=section_evidence,
        section_regions=section_regions,
        section_conflicts=section_conflicts,
        recognition_confidence=recognition_confidence,
        table2_amount_count=table2_amount_count,
        table3_check_values=table3_check_values,
        table3_check_row=table3_check_row,
        tb_reconciliation_detected=tb_reconciliation_detected,
        tb_reconciliation_confidence=tb_reconciliation_confidence,
        tb_difference_values=tb_difference_values,
        tb_difference_row=tb_difference_row,
        tb_notes_text_present=tb_notes_text_present,
        tb_notes_row=tb_notes_row,
        tb_notes_text=tb_notes_text,
        table4_pl_amounts=table4_pl_amounts,
        table4_pl_total=table4_pl_total,
        table4_pl_total_row=table4_pl_total_row,
        table4_rollforward_depreciation=table4_rollforward_depreciation,
        table4_rollforward_depreciation_row=table4_rollforward_depreciation_row,
        table4_difference=table4_difference,
        table4_difference_row=table4_difference_row,
        table4_notes_text_present=table4_notes_text_present,
        table4_notes_row=table4_notes_row,
        table4_notes_text=table4_notes_text,
        notes=notes,
    )


def load_rollforward_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 150,
) -> RollforwardSheetDataset:
    path = Path(path)
    if sheet_name:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            rows = read_worksheet_rows(wb[sheet_name], max_rows=max_rows)
        finally:
            wb.close()
        return parse_rollforward_rows(
            rows,
            source_file=str(path),
            source_sheet=sheet_name,
        )

    candidates = find_sheets_by_kind(path, SheetKind.ROLLFORWARD, max_rows=max_rows or 150)
    if not candidates:
        return RollforwardSheetDataset(
            source_file=str(path),
            source_sheet="",
            header_row=None,
            mapped_fields=[],
        )
    chosen = _choose_rollforward_candidate(candidates)
    return parse_rollforward_rows(
        chosen.rows,
        source_file=str(path),
        source_sheet=chosen.sheet_name,
    )
