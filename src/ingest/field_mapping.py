from __future__ import annotations

import re

from ingest.constants import (
    BLOCKED_ASSET_ID_HEADERS,
    FA_LIST_RECOMMENDED,
    FA_LIST_REQUIRED,
    FA_LIST_REQUIRED_IDENTITY,
    FIELD_SYNONYMS,
    REQUIRED_BY_KIND,
)
from ingest.field_mapping_policy import (
    DISALLOWED_FIELDS_BY_KIND,
    SHEET_FIELD_SYNONYM_EXTRAS,
    SHORT_SYNONYM_MAX_LEN,
    USEFUL_LIFE_HEADER_BLOCK_TOKENS,
)
from ingest.models import FieldMapping, SheetKind


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text).replace("\n", "").replace("\r", "")).lower()


def _field_allowed(field: str, sheet_kind: SheetKind | None) -> bool:
    if sheet_kind is None:
        return True
    blocked = DISALLOWED_FIELDS_BY_KIND.get(sheet_kind)
    if blocked and field in blocked:
        return False
    return True


def _useful_life_blocked(raw_header: str, synonym: str) -> bool:
    """避免将「资本开始折旧日期…」误映射为使用寿命。"""
    if any(tok in raw_header for tok in USEFUL_LIFE_HEADER_BLOCK_TOKENS):
        life_markers = ("(月)", "（月）", "年限", "期间", "年期")
        if not any(m in synonym for m in life_markers):
            return True
    return False


def _synonym_matches_header(n_header: str, n_syn: str, raw_header: str, field: str, syn: str) -> bool:
    if not n_syn:
        return False
    if len(n_syn) <= SHORT_SYNONYM_MAX_LEN:
        return n_header == n_syn
    if n_header == n_syn:
        return True
    if field == "useful_life_months" and _useful_life_blocked(raw_header, syn):
        return False
    if n_syn in n_header or n_header in n_syn:
        return True
    return False


def match_standard_field(
    cell_value: str,
    sheet_kind: SheetKind | None = None,
) -> str | None:
    """将表头单元格映射到标准字段名。"""
    raw = str(cell_value).strip()
    if not raw or len(raw) > 120:
        return None
    n = _norm(raw)

    if sheet_kind == SheetKind.DISPOSAL_LIST and raw in BLOCKED_ASSET_ID_HEADERS:
        return None
    if raw in BLOCKED_ASSET_ID_HEADERS and "单据" in raw:
        return None

    def _synonyms_for_field(field: str) -> list[str]:
        syns = list(FIELD_SYNONYMS.get(field, []))
        if sheet_kind and sheet_kind in SHEET_FIELD_SYNONYM_EXTRAS:
            syns.extend(SHEET_FIELD_SYNONYM_EXTRAS[sheet_kind].get(field, []))
        return syns

    best: str | None = None
    best_score = -1
    for field in FIELD_SYNONYMS:
        if not _field_allowed(field, sheet_kind):
            continue
        for syn in _synonyms_for_field(field):
            ns = _norm(syn)
            if not _synonym_matches_header(n, ns, raw, field, syn):
                continue
            score = (1000 if n == ns else 0) + len(ns)
            if score > best_score:
                best = field
                best_score = score
    return best


def map_headers(
    header_cells: list[tuple[int, str]],
    sheet_kind: SheetKind | None = None,
) -> tuple[list[FieldMapping], list[str]]:
    """header_cells: (col_index, text). 返回映射列表与未映射表头。"""
    mapped: dict[str, FieldMapping] = {}
    unmapped: list[str] = []
    for col, text in header_cells:
        field = match_standard_field(text, sheet_kind)
        if field and field not in mapped:
            mapped[field] = FieldMapping(
                standard_field=field,
                source_header=text.strip(),
                column_index=col,
            )
        elif text.strip() and not field:
            if len(text.strip()) <= 80 and not text.strip().startswith("获取"):
                unmapped.append(text.strip())
    return list(mapped.values()), unmapped


def check_required_fields(
    mapped_fields: list[FieldMapping],
    sheet_kind: SheetKind,
) -> tuple[list[str], list[str]]:
    """返回 (missing_required, missing_recommended)。"""
    present = {m.standard_field for m in mapped_fields}
    missing_req: list[str] = []
    missing_rec: list[str] = []

    if sheet_kind == SheetKind.FA_LIST:
        if not (FA_LIST_REQUIRED_IDENTITY[0] in present or FA_LIST_REQUIRED_IDENTITY[1] in present):
            missing_req.append("asset_id|asset_name")
        for f in FA_LIST_REQUIRED:
            if f not in present:
                missing_req.append(f)
        for f in FA_LIST_RECOMMENDED:
            if f not in present:
                missing_rec.append(f)
        return missing_req, missing_rec

    required = REQUIRED_BY_KIND.get(sheet_kind, [])
    for f in required:
        if f not in present:
            missing_req.append(f)
    return missing_req, missing_rec
