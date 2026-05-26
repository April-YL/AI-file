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

    ending: dict[str, Decimal | None] = {}
    opening: dict[str, Decimal | None] = {}
    total_row: int | None = None
    notes: list[str] = []
    if any(
        b.period_role in (RollforwardPeriodRole.OPENING, RollforwardPeriodRole.ENDING)
        for b in bindings
    ):
        notes.append("period_labels_applied")
    total_row_data: tuple[Any, ...] | None = None

    if header_row and (col_by_field or bindings):
        start = header_row
        for r_idx in range(start, len(rows)):
            row = rows[r_idx]
            if row is None or not _row_has_total_label(row):
                continue
            if not _row_plausible_total(row, col_by_field, bindings):
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
                elif col_by_field:
                    ending = _extract_totals_from_row(total_row_data, col_by_field)
            notes.append("totals_from_period_bindings")
        elif col_by_field:
            ending = _extract_totals_from_row(total_row_data, col_by_field)
            notes.append("ending_from_total_row")
        elif bindings:
            ending = _extract_totals_from_bindings(
                total_row_data, bindings, RollforwardPeriodRole.UNKNOWN
            )
            if _binding_totals_have_values(ending):
                notes.append("ending_from_total_row_unknown_binding")

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
