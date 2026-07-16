from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ingest.constants import (
    BLOCKED_ASSET_ID_HEADERS,
    FA_LIST_RECOMMENDED,
    FA_LIST_REQUIRED,
    FA_LIST_REQUIRED_IDENTITY,
    FIELD_SYNONYMS,
    REQUIRED_BY_KIND,
)
from ingest.field_mapping_policy import (
    BLOCKED_HEADER_FIELD_BY_KIND,
    DISALLOWED_FIELDS_BY_KIND,
    SHEET_FIELD_HEADER_PRIORITIES,
    SHEET_FIELD_SYNONYM_EXTRAS,
    SHORT_SYNONYM_MAX_LEN,
    USEFUL_LIFE_HEADER_BLOCK_TOKENS,
)
from ingest.models import (
    EvidenceType,
    FieldCandidate,
    FieldEvidence,
    FieldMapping,
    FieldResolutionDecision,
    ResolutionStatus,
    SheetKind,
)


_EVIDENCE_GATED_KINDS = {
    SheetKind.FA_LIST,
    SheetKind.ADDITION_LIST,
    SheetKind.DISPOSAL_LIST,
}
_CRITICAL_FIELDS = {
    "asset_id",
    "useful_life_months",
    "salvage_rate",
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "net_value",
}
_AMOUNT_FIELDS = {
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "net_value",
    "salvage_value",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text).replace("\n", "").replace("\r", "")).lower()


def _field_allowed(field: str, sheet_kind: SheetKind | None) -> bool:
    if sheet_kind is None:
        return True
    blocked = DISALLOWED_FIELDS_BY_KIND.get(sheet_kind)
    if blocked and field in blocked:
        return False
    return True


def _header_field_blocked(raw_header: str, field: str, sheet_kind: SheetKind | None) -> bool:
    if sheet_kind is None:
        return False
    blocked_by_field = BLOCKED_HEADER_FIELD_BY_KIND.get(sheet_kind, {})
    blocked_headers = blocked_by_field.get(field)
    if not blocked_headers:
        return False
    n_header = _norm(raw_header)
    return any(_norm(header) == n_header for header in blocked_headers)


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
        if _header_field_blocked(raw, field, sheet_kind):
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


def _mapping_priority(text: str, field: str, sheet_kind: SheetKind | None) -> int:
    if sheet_kind is None:
        return 0
    priorities = SHEET_FIELD_HEADER_PRIORITIES.get(sheet_kind, {}).get(field, ())
    if not priorities:
        return 0
    n_text = _norm(text)
    for index, header in enumerate(priorities):
        if _norm(header) == n_text:
            return len(priorities) - index
    return 0


def map_headers(
    header_cells: list[tuple[int, str]],
    sheet_kind: SheetKind | None = None,
) -> tuple[list[FieldMapping], list[str]]:
    """header_cells: (col_index, text). 返回映射列表与未映射表头。"""
    mapped: dict[str, FieldMapping] = {}
    unmapped: list[str] = []
    for col, text in header_cells:
        field = match_standard_field(text, sheet_kind)
        if field:
            candidate = FieldMapping(
                standard_field=field,
                source_header=text.strip(),
                column_index=col,
            )
            existing = mapped.get(field)
            if existing is None or _mapping_priority(
                candidate.source_header,
                field,
                sheet_kind,
            ) > _mapping_priority(existing.source_header, field, sheet_kind):
                mapped[field] = candidate
        elif text.strip() and not field:
            if len(text.strip()) <= 80 and not text.strip().startswith("获取"):
                unmapped.append(text.strip())
    return list(mapped.values()), unmapped


def _column_values(rows: list | None, column: int, header_row: int | None) -> list[object]:
    if not rows:
        return []
    start = header_row or 1
    values: list[object] = []
    for row in rows[start : start + 40]:
        if row is None or column - 1 >= len(row):
            continue
        value = row[column - 1]
        if value is not None and str(value).strip():
            values.append(value)
    return values


def _as_decimal(value: object) -> Decimal | None:
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _value_evidence(
    *,
    field: str,
    header: str,
    column: int,
    values: list[object],
    number_formats: dict[int, list[str]] | None,
    source_sheet: str | None,
) -> tuple[list[FieldEvidence], list[FieldEvidence]]:
    positive: list[FieldEvidence] = []
    negative: list[FieldEvidence] = []
    if not values:
        return positive, negative
    location = {"source_sheet": source_sheet, "column": column}
    decimals = [_as_decimal(value) for value in values]
    numeric = [value for value in decimals if value is not None]
    numeric_ratio = len(numeric) / len(values)

    if field in _AMOUNT_FIELDS and numeric_ratio >= 0.8:
        positive.append(FieldEvidence(EvidenceType.VALUE_TYPE, "sample values are predominantly numeric", **location))
    if field in _AMOUNT_FIELDS and all(re.fullmatch(r"[A-Za-z]{3}", str(value).strip()) for value in values):
        negative.append(FieldEvidence(EvidenceType.VALUE_TYPE, "currency-code values cannot serve as an amount column", **location))
    if field == "asset_id":
        text_values = [str(value).strip() for value in values]
        distinct_ratio = len(set(text_values)) / len(text_values)
        if distinct_ratio >= 0.8:
            positive.append(
                FieldEvidence(
                    EvidenceType.VALUE_DISTRIBUTION,
                    f"sample identifiers are predominantly distinct ({distinct_ratio:.0%})",
                    **location,
                )
            )
        normalized_header = re.sub(r"[\s_\-/]+", "", header).casefold()
        if (
            len(text_values) >= 10
            and distinct_ratio < 0.2
            and normalized_header in {"编号", "编码", "id", "code"}
        ):
            negative.append(
                FieldEvidence(
                    EvidenceType.VALUE_DISTRIBUTION,
                    f"generic identifier has an extremely low distinct ratio ({distinct_ratio:.0%})",
                    **location,
                )
            )
    if field == "useful_life_months" and numeric_ratio >= 0.8:
        positive.append(FieldEvidence(EvidenceType.VALUE_TYPE, "sample useful-life values are numeric", **location))
        if "年" in header and "月" not in header:
            negative.append(FieldEvidence(EvidenceType.STRUCTURAL_CONTEXT, "year-based header does not establish a month-based field", **location))
    if field == "salvage_rate" and numeric_ratio >= 0.8:
        formats = number_formats.get(column, []) if number_formats else []
        percent_marked = any("%" in str(value) for value in values) or any("%" in fmt for fmt in formats)
        if percent_marked or all(Decimal("0") <= value <= Decimal("1") for value in numeric):
            positive.append(FieldEvidence(EvidenceType.VALUE_TYPE, "rate scale is supported by values or percentage format", **location))
        elif any(value > Decimal("1") for value in numeric):
            negative.append(FieldEvidence(EvidenceType.VALUE_TYPE, "numeric rate above 1 has no confirmed percentage scale", **location))
    return positive, negative


def resolve_fields(
    header_cells: list[tuple[int, str]],
    sheet_kind: SheetKind | None = None,
    *,
    rows: list | None = None,
    header_row: int | None = None,
    number_formats: dict[int, list[str]] | None = None,
    source_sheet: str | None = None,
) -> dict[str, FieldResolutionDecision]:
    """Resolve candidate columns with auditable evidence; does not change map_headers."""
    candidates_by_field: dict[str, list[FieldCandidate]] = {}
    recognized_columns = {
        col for col, text in header_cells if match_standard_field(text, sheet_kind) is not None
    }
    for column, raw_header in header_cells:
        header = str(raw_header).strip()
        field = match_standard_field(header, sheet_kind)
        if field is None:
            continue
        evidence = [
            FieldEvidence(
                EvidenceType.HEADER_SEMANTIC,
                "header matches the standard-field vocabulary",
                source_sheet=source_sheet,
                row=header_row,
                column=column,
            )
        ]
        negative: list[FieldEvidence] = []
        if any(abs(column - other) <= 2 for other in recognized_columns if other != column):
            evidence.append(
                FieldEvidence(
                    EvidenceType.STRUCTURAL_CONTEXT,
                    "candidate is adjacent to other recognized business fields",
                    source_sheet=source_sheet,
                    row=header_row,
                    column=column,
                )
            )
        value_evidence, value_negative = _value_evidence(
            field=field,
            header=header,
            column=column,
            values=_column_values(rows, column, header_row),
            number_formats=number_formats,
            source_sheet=source_sheet,
        )
        evidence.extend(value_evidence)
        negative.extend(value_negative)
        if field == "asset_id" and "旧" in header:
            negative.append(
                FieldEvidence(
                    EvidenceType.HEADER_SEMANTIC,
                    "legacy asset identifier cannot be adopted as the current unique identifier by name alone",
                    source_sheet=source_sheet,
                    row=header_row,
                    column=column,
                )
            )
        evidence_types = {item.evidence_type for item in evidence}
        candidates_by_field.setdefault(field, []).append(
            FieldCandidate(
                standard_field=field,
                source_header=header,
                column_index=column,
                evidence=evidence,
                negative_evidence=negative,
                confidence=min(1.0, 0.35 + 0.2 * len(evidence_types) - 0.25 * len(negative)),
            )
        )

    decisions: dict[str, FieldResolutionDecision] = {}
    all_fields = set(FIELD_SYNONYMS) | set(candidates_by_field)
    for field in all_fields:
        candidates = candidates_by_field.get(field, [])
        decision = FieldResolutionDecision(
            standard_field=field,
            candidates=candidates,
            source_sheet=source_sheet,
        )
        valid = [candidate for candidate in candidates if not candidate.negative_evidence]
        if not candidates:
            decision.status = ResolutionStatus.MISSING
            decision.rejection_reasons.append("no deterministic header candidate")
        elif not valid:
            decision.status = ResolutionStatus.INVALID
            decision.negative_evidence = [item for candidate in candidates for item in candidate.negative_evidence]
            decision.rejection_reasons.append("all candidates contain blocking negative evidence")
        else:
            required_count = 2 if sheet_kind in _EVIDENCE_GATED_KINDS and field in _CRITICAL_FIELDS else 1
            qualified = [
                candidate
                for candidate in valid
                if len({item.evidence_type for item in candidate.evidence}) >= required_count
            ]
            if not qualified:
                decision.status = ResolutionStatus.INVALID
                decision.rejection_reasons.append(
                    f"fewer than {required_count} independent evidence types"
                )
            elif len(qualified) > 1:
                best = max(candidate.confidence for candidate in qualified)
                leaders = [candidate for candidate in qualified if candidate.confidence == best]
                if len(leaders) != 1:
                    decision.status = ResolutionStatus.AMBIGUOUS
                    decision.rejection_reasons.append("multiple equally supported candidates")
                else:
                    decision.status = ResolutionStatus.RESOLVED
                    decision.selected_candidate = leaders[0]
            else:
                decision.status = ResolutionStatus.RESOLVED
                decision.selected_candidate = qualified[0]
            if decision.selected_candidate is not None:
                selected = decision.selected_candidate
                decision.evidence = list(selected.evidence)
                decision.negative_evidence = list(selected.negative_evidence)
                decision.header = selected.source_header
                decision.row = header_row
                decision.column = selected.column_index
                decision.acceptance_reason = "selected from deterministic candidates using independent evidence"
        decisions[field] = decision
    return decisions


def resolved_mappings(decisions: dict[str, FieldResolutionDecision]) -> list[FieldMapping]:
    return [
        FieldMapping(
            standard_field=decision.standard_field,
            source_header=decision.selected_candidate.source_header,
            column_index=decision.selected_candidate.column_index,
        )
        for decision in decisions.values()
        if decision.status == ResolutionStatus.RESOLVED
        and decision.selected_candidate is not None
    ]


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
