from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

from ingest.field_mapping import map_headers
from ingest.header_detection import scan_rows_for_headers
from ingest.models import FieldMapping, SheetKind
from ingest.sheet_classifier import classify_sheet
from ingest.workbook_reader import read_worksheet_rows

K03_BRANCH_DEPRECIATION_TEST = "depreciation_test"
K03_BRANCH_POLICY_REVIEW = "depreciation_policy_review"

EXECUTION_PATH_SAP_MEDIUM = "sap_medium_precision"
EXECUTION_PATH_SAP_HIGH = "sap_high_precision"
EXECUTION_PATH_TOD_SAMPLING = "tod_sampling"
EXECUTION_PATH_TOD_BY_ITEM = "tod_by_item"
EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING = "sap_plus_tod_sampling"
EXECUTION_PATH_POLICY_REVIEW = "policy_review"
EXECUTION_PATH_UNKNOWN = "unknown"

INGEST_DEPTH_DETAILED = "detailed"
INGEST_DEPTH_LIGHTWEIGHT = "lightweight"
INGEST_DEPTH_TEMPLATE_DETECTION = "template_detection"

RULE_STATUS_READY_FOR_LATER_RULES = "ready_for_later_rules"
RULE_STATUS_LATER_PHASE = "later_phase"

_K03_KINDS = {
    SheetKind.DEPRECIATION_TOD,
    SheetKind.DEPRECIATION_TOD_SAMPLE,
    SheetKind.SAP,
    SheetKind.DEPRECIATION_POLICY,
}

_AMOUNT_FIELDS = {
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "net_value",
    "current_depreciation",
    "management_depreciation",
    "audit_recalculated_depreciation",
    "depreciation_difference",
}
_DATE_FIELDS = {"start_date", "depreciation_start_date", "disposal_date"}
_BY_ITEM_CORE_FIELDS = {
    "asset_id",
    "asset_name",
    "original_value",
    "useful_life_months",
    "salvage_rate",
}


@dataclass
class K03Area:
    start_row: int | None = None
    end_row: int | None = None
    start_col: int | None = None
    end_col: int | None = None
    text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_row": self.start_row,
            "end_row": self.end_row,
            "start_col": self.start_col,
            "end_col": self.end_col,
            "text": self.text,
        }


@dataclass
class K03Column:
    source_header: str
    column_index: int
    column_letter: str
    standard_field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_header": self.source_header,
            "column_index": self.column_index,
            "column_letter": self.column_letter,
            "standard_field": self.standard_field,
        }


@dataclass
class K03DetailRow:
    source_row: int
    raw_values: dict[str, Any] = field(default_factory=dict)
    normalized_values: dict[str, Any] = field(default_factory=dict)
    cell_refs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "raw_values": self.raw_values,
            "normalized_values": self.normalized_values,
            "cell_refs": self.cell_refs,
        }


@dataclass
class K03DetailTableRef:
    source_file: str
    sheet_name: str
    start_row: int | None = None
    end_row: int | None = None
    start_col: int | None = None
    end_col: int | None = None
    header_row: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "sheet_name": self.sheet_name,
            "start_row": self.start_row,
            "end_row": self.end_row,
            "start_col": self.start_col,
            "end_col": self.end_col,
            "header_row": self.header_row,
        }


@dataclass
class K03DetailTable:
    detail_rows: list[K03DetailRow] = field(default_factory=list)
    total_rows: list[K03DetailRow] = field(default_factory=list)


@dataclass
class K03PolicyRow:
    source_row: int
    asset_category: Any = None
    current_method: Any = None
    current_useful_life: Any = None
    current_salvage_rate: Any = None
    current_annual_rate: Any = None
    prior_method: Any = None
    prior_useful_life: Any = None
    prior_salvage_rate: Any = None
    prior_annual_rate: Any = None
    useful_life_same_marker: Any = None
    salvage_rate_same_marker: Any = None
    difference_explanation: Any = None
    cell_refs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "asset_category": self.asset_category,
            "current_method": self.current_method,
            "current_useful_life": self.current_useful_life,
            "current_salvage_rate": self.current_salvage_rate,
            "current_annual_rate": self.current_annual_rate,
            "prior_method": self.prior_method,
            "prior_useful_life": self.prior_useful_life,
            "prior_salvage_rate": self.prior_salvage_rate,
            "prior_annual_rate": self.prior_annual_rate,
            "useful_life_same_marker": self.useful_life_same_marker,
            "salvage_rate_same_marker": self.salvage_rate_same_marker,
            "difference_explanation": self.difference_explanation,
            "cell_refs": self.cell_refs,
        }


@dataclass
class K03PolicyTable:
    range: K03Area | None = None
    header_row: int | None = None
    column_map: dict[str, K03Column] = field(default_factory=dict)
    rows: list[K03PolicyRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "range": self.range.to_dict() if self.range else None,
            "header_row": self.header_row,
            "column_map": {k: v.to_dict() for k, v in self.column_map.items()},
            "rows": [r.to_dict() for r in self.rows],
            "warnings": self.warnings,
        }


@dataclass
class K03SheetDataset:
    workbook_name: str
    source_file: str
    sheet_name: str
    k03_branch: str
    execution_path: str = EXECUTION_PATH_UNKNOWN
    template_type: str = "unknown"
    ingest_depth: str = INGEST_DEPTH_LIGHTWEIGHT
    rule_status: str = RULE_STATUS_LATER_PHASE
    detected_sections: list[str] = field(default_factory=list)
    header_rows: list[int] = field(default_factory=list)
    detail_table_ref: K03DetailTableRef | None = None
    detail_table_range: K03Area | None = None
    total_rows: list[int] = field(default_factory=list)
    conclusion_area: K03Area | None = None
    note_area: K03Area | None = None
    instruction_area: K03Area | None = None
    policy_table: K03PolicyTable | None = None
    raw_columns: list[K03Column] = field(default_factory=list)
    normalized_column_map: dict[str, K03Column] = field(default_factory=dict)
    unmapped_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    amount_columns: list[str] = field(default_factory=list)
    date_columns: list[str] = field(default_factory=list)
    unsupported_or_later_phase: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    preview_rows: list[dict[str, Any]] = field(default_factory=list)
    llm_candidate_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workbook_name": self.workbook_name,
            "source_file": self.source_file,
            "sheet_name": self.sheet_name,
            "k03_branch": self.k03_branch,
            "execution_path": self.execution_path,
            "template_type": self.template_type,
            "ingest_depth": self.ingest_depth,
            "rule_status": self.rule_status,
            "detected_sections": self.detected_sections,
            "header_rows": self.header_rows,
            "detail_table_ref": (
                self.detail_table_ref.to_dict() if self.detail_table_ref else None
            ),
            "detail_table_range": (
                self.detail_table_range.to_dict() if self.detail_table_range else None
            ),
            "total_rows": self.total_rows,
            "conclusion_area": (
                self.conclusion_area.to_dict() if self.conclusion_area else None
            ),
            "note_area": self.note_area.to_dict() if self.note_area else None,
            "instruction_area": (
                self.instruction_area.to_dict() if self.instruction_area else None
            ),
            "policy_table": self.policy_table.to_dict() if self.policy_table else None,
            "raw_columns": [c.to_dict() for c in self.raw_columns],
            "normalized_column_map": {
                k: v.to_dict() for k, v in self.normalized_column_map.items()
            },
            "unmapped_columns": self.unmapped_columns,
            "warnings": self.warnings,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "amount_columns": self.amount_columns,
            "date_columns": self.date_columns,
            "unsupported_or_later_phase": self.unsupported_or_later_phase,
            "summary": self.summary,
            "preview_rows": self.preview_rows,
            "llm_candidate_context": self.llm_candidate_context,
        }


def load_k03_sheets_from_workbook(
    path: str | Path,
    *,
    max_rows: int | None = None,
) -> list[K03SheetDataset]:
    path = Path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    datasets: list[K03SheetDataset] = []
    try:
        for ws in wb.worksheets:
            preview_rows = read_worksheet_rows(ws, max_rows=max_rows or 200)
            kind, confidence, *_ = classify_sheet(ws.title, preview_rows)
            if kind not in _K03_KINDS and not _looks_like_k03_sheet(ws.title):
                continue
            rows = read_worksheet_rows(ws, max_rows=None)
            datasets.append(
                _parse_k03_sheet(
                    path=path,
                    sheet_name=ws.title,
                    rows=rows,
                    classified_kind=kind,
                    classification_confidence=confidence,
                )
            )
    finally:
        wb.close()
    return datasets


def load_k03_detail_table(dataset: K03SheetDataset) -> K03DetailTable:
    """Read full K.03 TOD-by item details only when deterministic rules need them."""
    ref = dataset.detail_table_ref
    if ref is None or not ref.source_file or not ref.sheet_name:
        return K03DetailTable()
    if not ref.header_row or not ref.start_row or not ref.end_row:
        return K03DetailTable()

    wb = openpyxl.load_workbook(ref.source_file, read_only=True, data_only=True)
    try:
        if ref.sheet_name not in wb.sheetnames:
            return K03DetailTable()
        ws = wb[ref.sheet_name]
        header_by_col = {
            col.column_index: col.source_header
            for col in dataset.raw_columns
            if col.column_index is not None
        }
        field_by_col = {
            col.column_index: field
            for field, col in dataset.normalized_column_map.items()
            if col.column_index is not None
        }
        if not header_by_col:
            return K03DetailTable()

        detail_rows: list[K03DetailRow] = []
        total_rows: list[K03DetailRow] = []
        read_start = (ref.header_row or ref.start_row) + 1
        min_col = min(header_by_col)
        max_col = max(header_by_col)
        row_iter = ws.iter_rows(
            min_row=read_start,
            max_row=ref.end_row,
            min_col=min_col,
            max_col=max_col,
            values_only=True,
        )
        for row_number, row_values in zip(range(read_start, ref.end_row + 1), row_iter):
            raw_values: dict[str, Any] = {}
            normalized_values: dict[str, Any] = {}
            cell_refs: dict[str, str] = {}
            for col in sorted(header_by_col):
                header = header_by_col[col]
                value = row_values[col - min_col]
                raw_values[header] = value
                field = field_by_col.get(col)
                if field:
                    normalized_values[field] = value
                    cell_refs[field] = f"{get_column_letter(col)}{row_number}"
            if _is_blank(raw_values.values()):
                continue
            row = K03DetailRow(
                source_row=row_number,
                raw_values=raw_values,
                normalized_values=normalized_values,
                cell_refs=cell_refs,
            )
            if row_number in dataset.total_rows or _row_has_token(
                raw_values.values(),
                ("合计", "总计", "小计", "total"),
            ):
                total_rows.append(row)
            else:
                detail_rows.append(row)
        return K03DetailTable(detail_rows=detail_rows, total_rows=total_rows)
    finally:
        wb.close()


def _parse_k03_sheet(
    *,
    path: Path,
    sheet_name: str,
    rows: list[tuple[Any, ...]],
    classified_kind: SheetKind,
    classification_confidence: float,
) -> K03SheetDataset:
    if _is_policy_review(sheet_name, rows, classified_kind):
        return _parse_policy_review(path, sheet_name, rows, classification_confidence)
    if _is_sap_sheet(sheet_name, classified_kind):
        return _parse_sap_sheet(path, sheet_name, rows)
    return _parse_tod_sheet(path, sheet_name, rows, classified_kind)


def _parse_policy_review(
    path: Path,
    sheet_name: str,
    rows: list[tuple[Any, ...]],
    confidence: float,
) -> K03SheetDataset:
    text_rows = _rows_containing(rows, ("政策", "折旧", "结论", "说明", "复核"))
    conclusion = _area_for_rows(rows, _rows_containing(rows, ("结论",)))
    policy_table = _extract_policy_table(rows)
    note = _detect_policy_note_area(rows, policy_table.range if policy_table else None)
    detected_sections = ["policy_review"]
    if policy_table and policy_table.rows:
        detected_sections.append("policy_table")
    if note:
        detected_sections.append("note_area")
    warnings = [] if confidence >= 0.45 else ["k03_policy_review_low_confidence"]
    if policy_table is None or not policy_table.rows:
        warnings.append("k03_policy_table_not_identified")
    elif policy_table.warnings:
        warnings.extend(policy_table.warnings)
    ds = K03SheetDataset(
        workbook_name=path.name,
        source_file=str(path),
        sheet_name=sheet_name,
        k03_branch=K03_BRANCH_POLICY_REVIEW,
        execution_path=EXECUTION_PATH_POLICY_REVIEW,
        template_type="policy_review",
        ingest_depth=INGEST_DEPTH_LIGHTWEIGHT,
        rule_status=RULE_STATUS_LATER_PHASE,
        detected_sections=detected_sections,
        conclusion_area=conclusion,
        note_area=note,
        policy_table=policy_table,
        warnings=warnings,
        summary={
            "text_row_count": len(text_rows),
            "policy_row_count": len(policy_table.rows) if policy_table else 0,
            "has_policy_table": bool(policy_table and policy_table.rows),
            "has_note_area": note is not None,
        },
        unsupported_or_later_phase=False,
        llm_candidate_context={
            "text_rows": text_rows[:20],
            "warnings": warnings,
            "candidate_for": "depreciation_policy_semantic_review",
            "policy_table_summary": {
                "row_count": len(policy_table.rows) if policy_table else 0,
                "mapped_fields": sorted(policy_table.column_map) if policy_table else [],
            },
        },
    )
    return ds


def _extract_policy_table(rows: list[tuple[Any, ...]]) -> K03PolicyTable | None:
    header_row, column_map, warnings = _detect_policy_header(rows)
    if not header_row or not column_map:
        return None
    required = {"asset_category", "current_useful_life", "prior_useful_life"}
    if not (required & set(column_map)):
        warnings.append("k03_policy_table_core_columns_missing")

    row_items: list[K03PolicyRow] = []
    end_row = header_row
    max_col = max(c.column_index for c in column_map.values())
    min_col = min(c.column_index for c in column_map.values())
    for idx in range(header_row, len(rows)):
        row_number = idx + 1
        row = rows[idx]
        values = {
            field: _cell_value(row, col.column_index)
            for field, col in column_map.items()
        }
        if _is_blank(values.values()):
            if row_items:
                break
            continue
        if _row_has_token(row, ("Notes", "注：", "注:", "说明", "结论")) and row_items:
            break
        category = values.get("asset_category")
        if not _text(category):
            if row_items:
                break
            continue
        if _looks_like_policy_non_data_row(category):
            if row_items:
                break
            continue

        cell_refs = {
            field: f"{get_column_letter(col.column_index)}{row_number}"
            for field, col in column_map.items()
        }
        row_items.append(
            K03PolicyRow(
                source_row=row_number,
                asset_category=category,
                current_method=values.get("current_method"),
                current_useful_life=values.get("current_useful_life"),
                current_salvage_rate=values.get("current_salvage_rate"),
                current_annual_rate=values.get("current_annual_rate"),
                prior_method=values.get("prior_method"),
                prior_useful_life=values.get("prior_useful_life"),
                prior_salvage_rate=values.get("prior_salvage_rate"),
                prior_annual_rate=values.get("prior_annual_rate"),
                useful_life_same_marker=values.get("useful_life_same_marker"),
                salvage_rate_same_marker=values.get("salvage_rate_same_marker"),
                difference_explanation=values.get("difference_explanation"),
                cell_refs=cell_refs,
            )
        )
        end_row = row_number

    return K03PolicyTable(
        range=K03Area(
            start_row=header_row,
            end_row=end_row,
            start_col=min_col,
            end_col=max_col,
        ),
        header_row=header_row,
        column_map=column_map,
        rows=row_items,
        warnings=warnings,
    )


def _detect_policy_header(
    rows: list[tuple[Any, ...]],
) -> tuple[int | None, dict[str, K03Column], list[str]]:
    best_row: int | None = None
    best_map: dict[str, K03Column] = {}
    best_score = 0
    warnings: list[str] = []
    for idx, row in enumerate(rows[:80], start=1):
        mapping = _map_policy_header_row(rows, idx)
        fields = set(mapping)
        score = len(fields & {
            "asset_category",
            "current_method",
            "current_useful_life",
            "current_salvage_rate",
            "prior_method",
            "prior_useful_life",
            "prior_salvage_rate",
            "useful_life_same_marker",
            "salvage_rate_same_marker",
            "difference_explanation",
        })
        if "asset_category" in fields:
            score += 2
        if {"current_useful_life", "prior_useful_life"} <= fields:
            score += 2
        if {"current_salvage_rate", "prior_salvage_rate"} <= fields:
            score += 2
        if score > best_score:
            best_row = idx
            best_map = mapping
            best_score = score
    if best_score < 4:
        return None, {}, ["k03_policy_table_header_not_identified"]
    return best_row, best_map, warnings


def _map_policy_header_row(
    rows: list[tuple[Any, ...]],
    row_number: int,
) -> dict[str, K03Column]:
    row = rows[row_number - 1]
    prev = rows[row_number - 2] if row_number >= 2 else ()
    mapping: dict[str, K03Column] = {}
    used_fields: set[str] = set()
    for col_idx, value in enumerate(row, start=1):
        header = _text(value)
        prev_header = _text(prev[col_idx - 1]) if col_idx - 1 < len(prev) else ""
        combined = " ".join(v for v in (prev_header, header) if v)
        field = _policy_field_for_header(combined, header, prev_header, used_fields)
        if not field:
            continue
        used_fields.add(field)
        mapping[field] = K03Column(
            source_header=combined or header,
            column_index=col_idx,
            column_letter=get_column_letter(col_idx),
            standard_field=field,
        )
    return mapping


def _policy_field_for_header(
    combined: str,
    header: str,
    prev_header: str,
    used_fields: set[str],
) -> str | None:
    n = _norm(combined)
    h = _norm(header)
    p = _norm(prev_header)
    if not n:
        return None
    if any(token in n for token in ("固定资产类别", "资产类别", "类别")) and "asset_category" not in used_fields:
        return "asset_category"
    is_prior = any(token in n for token in ("上期", "上年", "以前", "prior", "previous", "2024"))
    is_current = any(token in n for token in ("本期", "本年", "当前", "current", "2025")) or (
        not is_prior and any(token in p for token in ("本期", "本年", "current"))
    )
    is_difference = any(token in n for token in ("差异", "是否一致", "变化", "变动", "difference"))

    if any(token in n for token in ("差异说明", "说明", "备注", "原因", "解释", "note", "comment")):
        return "difference_explanation"
    if is_difference and any(token in n for token in ("寿命", "年限", "使用年限")):
        return "useful_life_same_marker"
    if is_difference and any(token in n for token in ("残值", "残值率")):
        return "salvage_rate_same_marker"
    if any(token in n for token in ("折旧方法", "折旧政策", "折旧方式")):
        return "prior_method" if is_prior else "current_method" if is_current or "current_method" not in used_fields else "prior_method"
    if any(token in n for token in ("使用寿命", "使用年限", "折旧年限", "寿命")):
        return "prior_useful_life" if is_prior else "current_useful_life" if is_current or "current_useful_life" not in used_fields else "prior_useful_life"
    if any(token in n for token in ("残值率", "净残值率", "残值")):
        return "prior_salvage_rate" if is_prior else "current_salvage_rate" if is_current or "current_salvage_rate" not in used_fields else "prior_salvage_rate"
    if any(token in n for token in ("年折旧率", "折旧率")):
        return "prior_annual_rate" if is_prior else "current_annual_rate" if is_current or "current_annual_rate" not in used_fields else "prior_annual_rate"
    # Two-level headers sometimes put only the metric in the leaf row.
    if h in {"折旧方法", "使用寿命", "使用年限", "残值率", "年折旧率"}:
        if "上期" in p or "prior" in p:
            prefix = "prior"
        else:
            prefix = "current"
        suffix = {
            "折旧方法": "method",
            "使用寿命": "useful_life",
            "使用年限": "useful_life",
            "残值率": "salvage_rate",
            "年折旧率": "annual_rate",
        }[h]
        return f"{prefix}_{suffix}"
    return None


def _detect_policy_note_area(
    rows: list[tuple[Any, ...]],
    policy_range: K03Area | None,
) -> K03Area | None:
    start = policy_range.end_row if policy_range and policy_range.end_row else 0
    matches: list[int] = []
    for idx, row in enumerate(rows, start=1):
        if idx <= start:
            continue
        if _row_has_token(row, ("Notes", "注：", "注:", "说明", "差异说明", "结论")):
            matches.append(idx)
    return _area_for_rows(rows, matches)


def _cell_value(row: tuple[Any, ...], col_index: int) -> Any:
    return row[col_index - 1] if col_index - 1 < len(row) else None


def _looks_like_policy_non_data_row(value: Any) -> bool:
    text = _text(value)
    if not text:
        return True
    lower = text.lower()
    return any(token in lower for token in ("合计", "小计", "总计", "notes", "说明", "结论", "表1"))


def _parse_sap_sheet(
    path: Path,
    sheet_name: str,
    rows: list[tuple[Any, ...]],
) -> K03SheetDataset:
    text = _combined_text(sheet_name, rows)
    if "高精确度" in text or "高精度" in text:
        execution_path = EXECUTION_PATH_SAP_HIGH
        template_type = "sap_high_precision"
    elif "中精确度" in text or "中精度" in text:
        execution_path = EXECUTION_PATH_SAP_MEDIUM
        template_type = "sap_medium_precision"
    else:
        execution_path = EXECUTION_PATH_UNKNOWN
        template_type = "sap"

    warnings = []
    if execution_path == EXECUTION_PATH_UNKNOWN:
        warnings.append("k03_sap_precision_not_identified")
    return K03SheetDataset(
        workbook_name=path.name,
        source_file=str(path),
        sheet_name=sheet_name,
        k03_branch=K03_BRANCH_DEPRECIATION_TEST,
        execution_path=execution_path,
        template_type=template_type,
        ingest_depth=INGEST_DEPTH_TEMPLATE_DETECTION,
        rule_status=RULE_STATUS_LATER_PHASE,
        detected_sections=["sap_template"],
        warnings=warnings,
        summary={"template_detection_only": True},
        unsupported_or_later_phase=True,
    )


def _parse_tod_sheet(
    path: Path,
    sheet_name: str,
    rows: list[tuple[Any, ...]],
    classified_kind: SheetKind,
) -> K03SheetDataset:
    header_row, header_cells, _ = scan_rows_for_headers(
        rows,
        sheet_kind=SheetKind.DEPRECIATION_TOD,
    )
    mapped_fields, unmapped = _map_k03_headers(header_cells)
    normalized = {m.standard_field: m for m in mapped_fields}
    raw_columns = [
        K03Column(
            source_header=text,
            column_index=col,
            column_letter=get_column_letter(col),
            standard_field=next(
                (m.standard_field for m in mapped_fields if m.column_index == col),
                None,
            ),
        )
        for col, text in header_cells
    ]
    by_item_score = _by_item_score(normalized)
    sample_score = _sample_score(sheet_name, rows, header_cells)
    warnings: list[str] = []

    if by_item_score >= 6 and sample_score < 3:
        execution_path = EXECUTION_PATH_TOD_BY_ITEM
        ingest_depth = INGEST_DEPTH_DETAILED
        template_type = "tod_by_item"
    elif by_item_score >= 7:
        execution_path = EXECUTION_PATH_TOD_BY_ITEM
        ingest_depth = INGEST_DEPTH_DETAILED
        template_type = "tod_by_item"
    elif sample_score >= 2 or (
        classified_kind == SheetKind.DEPRECIATION_TOD_SAMPLE and bool(header_cells)
    ):
        execution_path = EXECUTION_PATH_TOD_SAMPLING
        ingest_depth = INGEST_DEPTH_LIGHTWEIGHT
        template_type = "tod_sampling"
    else:
        execution_path = EXECUTION_PATH_UNKNOWN
        ingest_depth = INGEST_DEPTH_LIGHTWEIGHT
        template_type = "tod_unknown"
        warnings.append("k03_tod_execution_path_not_identified")

    detail_rows, detail_range, total_rows = _extract_detail_rows(
        rows,
        header_row=header_row,
        header_cells=header_cells,
        normalized=normalized,
    )
    conclusion = _detect_conclusion_area(rows, header_row, detail_range)
    note = _area_for_rows(rows, _rows_containing(rows, ("说明", "注：", "注:")))
    instruction = _area_for_rows(rows, _rows_containing(rows, ("获取", "编制", "按照", "根据")))
    detected_sections = []
    if header_row:
        detected_sections.append("header")
    if detail_range:
        detected_sections.append("detail_table")
    if total_rows:
        detected_sections.append("total_rows")
    if conclusion:
        detected_sections.append("conclusion_area")
    if note:
        detected_sections.append("note_area")
    if instruction:
        detected_sections.append("instruction_area")

    if unmapped:
        warnings.append("k03_unmapped_columns_present")
    missing_noncritical = sorted(_BY_ITEM_CORE_FIELDS - set(normalized))
    if execution_path == EXECUTION_PATH_TOD_BY_ITEM and missing_noncritical:
        warnings.append("k03_tod_by_item_missing_noncritical_fields:" + ",".join(missing_noncritical))

    preview_rows = [row.to_dict() for row in detail_rows[:5]]
    field_summary = {
        "raw_column_count": len(raw_columns),
        "mapped_field_count": len(normalized),
        "mapped_fields": sorted(normalized),
        "unmapped_column_count": len(unmapped),
        "amount_columns": sorted(set(normalized) & _AMOUNT_FIELDS),
        "date_columns": sorted(set(normalized) & _DATE_FIELDS),
    }
    table_ref = (
        K03DetailTableRef(
            source_file=str(path),
            sheet_name=sheet_name,
            start_row=detail_range.start_row,
            end_row=detail_range.end_row,
            start_col=detail_range.start_col,
            end_col=detail_range.end_col,
            header_row=header_row,
        )
        if detail_range
        else None
    )

    return K03SheetDataset(
        workbook_name=path.name,
        source_file=str(path),
        sheet_name=sheet_name,
        k03_branch=K03_BRANCH_DEPRECIATION_TEST,
        execution_path=execution_path,
        template_type=template_type,
        ingest_depth=ingest_depth,
        rule_status=RULE_STATUS_LATER_PHASE,
        detected_sections=detected_sections,
        header_rows=[header_row] if header_row else [],
        detail_table_ref=table_ref,
        detail_table_range=detail_range,
        total_rows=total_rows,
        conclusion_area=conclusion,
        note_area=note,
        instruction_area=instruction,
        raw_columns=raw_columns,
        normalized_column_map={
            field: K03Column(
                source_header=m.source_header,
                column_index=m.column_index,
                column_letter=get_column_letter(m.column_index),
                standard_field=m.standard_field,
            )
            for field, m in normalized.items()
        },
        unmapped_columns=unmapped,
        warnings=warnings,
        row_count=len(detail_rows),
        column_count=len(raw_columns),
        amount_columns=sorted(set(normalized) & _AMOUNT_FIELDS),
        date_columns=sorted(set(normalized) & _DATE_FIELDS),
        unsupported_or_later_phase=False,
        summary={
            **field_summary,
            "total_row_count": len(total_rows),
            "has_conclusion_area": conclusion is not None,
            "has_note_area": note is not None,
            "has_instruction_area": instruction is not None,
        },
        preview_rows=preview_rows,
        llm_candidate_context={
            "instruction_area": instruction.to_dict() if instruction else None,
            "note_area": note.to_dict() if note else None,
            "conclusion_area": conclusion.to_dict() if conclusion else None,
            "warnings": warnings,
            "field_summary": field_summary,
            "anomaly_row_refs": [],
            "preview_rows": preview_rows[:3],
        },
    )


def _map_k03_headers(header_cells: list[tuple[int, str]]) -> tuple[list[FieldMapping], list[str]]:
    mapped, unmapped = map_headers(header_cells, SheetKind.DEPRECIATION_TOD)
    used_cols = {m.column_index for m in mapped}
    extra_mapped: list[FieldMapping] = []
    extra_unmapped: list[str] = []
    for col, text in header_cells:
        if col in used_cols:
            continue
        field = _match_k03_extra_field(text)
        if field:
            extra_mapped.append(FieldMapping(field, text.strip(), col))
            used_cols.add(col)
        elif text.strip():
            extra_unmapped.append(text.strip())
    return mapped + extra_mapped, list(dict.fromkeys(unmapped + extra_unmapped))


def _match_k03_extra_field(text: str) -> str | None:
    n = _norm(text)
    if not n:
        return None
    checks = (
        ("management_depreciation", ("管理层计算折旧", "管理层测算折旧", "客户计算折旧", "账面折旧")),
        (
            "audit_recalculated_depreciation",
            ("审计重新计算折旧", "审计重算折旧", "审计测算折旧", "重新计算折旧"),
        ),
        ("depreciation_difference", ("差异", "差额", "diff", "difference")),
        ("depreciation_start_date", ("折旧起始日期", "开始折旧日期", "折旧开始日期")),
        ("conclusion", ("结论", "测试结论", "复核结论")),
        ("current_depreciation", ("本期折旧", "本年折旧", "本期计提折旧")),
    )
    for field, synonyms in checks:
        for synonym in synonyms:
            ns = _norm(synonym)
            if n == ns or ns in n or n in ns:
                return field
    return None


def _extract_detail_rows(
    rows: list[tuple[Any, ...]],
    *,
    header_row: int | None,
    header_cells: list[tuple[int, str]],
    normalized: dict[str, FieldMapping],
) -> tuple[list[K03DetailRow], K03Area | None, list[int]]:
    if not header_row or not header_cells:
        return [], None, []

    header_by_col = {col: text for col, text in header_cells}
    field_by_col = {m.column_index: m.standard_field for m in normalized.values()}
    min_col = min(header_by_col)
    max_col = max(header_by_col)
    detail_rows: list[K03DetailRow] = []
    total_rows: list[int] = []
    end_row = header_row

    for idx in range(header_row, len(rows)):
        row_number = idx + 1
        row = rows[idx]
        values = {col: row[col - 1] if col - 1 < len(row) else None for col in header_by_col}
        if _is_blank(values.values()):
            if detail_rows:
                break
            continue
        if _row_has_token(values.values(), ("结论", "说明", "注：", "注:")) and not detail_rows:
            continue
        if _row_has_token(values.values(), ("合计", "总计", "小计", "total")):
            total_rows.append(row_number)
            end_row = row_number
            continue
        if _row_has_token(values.values(), ("结论",)) and detail_rows:
            break

        raw_values: dict[str, Any] = {}
        normalized_values: dict[str, Any] = {}
        cell_refs: dict[str, str] = {}
        for col, header in header_by_col.items():
            value = values.get(col)
            raw_values[header] = value
            field = field_by_col.get(col)
            if field:
                normalized_values[field] = value
                cell_refs[field] = f"{get_column_letter(col)}{row_number}"
        if not _is_blank(raw_values.values()):
            detail_rows.append(
                K03DetailRow(
                    source_row=row_number,
                    raw_values=raw_values,
                    normalized_values=normalized_values,
                    cell_refs=cell_refs,
                )
            )
            end_row = row_number

    if not detail_rows and not total_rows:
        return [], None, []
    start_row = detail_rows[0].source_row if detail_rows else total_rows[0]
    return (
        detail_rows,
        K03Area(start_row=start_row, end_row=end_row, start_col=min_col, end_col=max_col),
        total_rows,
    )


def _detect_conclusion_area(
    rows: list[tuple[Any, ...]],
    header_row: int | None,
    detail_range: K03Area | None,
) -> K03Area | None:
    start = detail_range.end_row if detail_range and detail_range.end_row else header_row or 0
    matches = []
    for idx, row in enumerate(rows, start=1):
        if idx <= start:
            continue
        if _row_has_token(row, ("结论", "未见异常", "可以接受", "无需调整")):
            matches.append(idx)
    return _area_for_rows(rows, matches)


def _area_for_rows(rows: list[tuple[Any, ...]], row_numbers: list[int]) -> K03Area | None:
    if not row_numbers:
        return None
    texts = []
    start_col = None
    end_col = None
    for row_number in row_numbers:
        row = rows[row_number - 1]
        for col, value in enumerate(row, start=1):
            text = _text(value)
            if not text:
                continue
            texts.append(text)
            start_col = col if start_col is None else min(start_col, col)
            end_col = col if end_col is None else max(end_col, col)
    return K03Area(
        start_row=min(row_numbers),
        end_row=max(row_numbers),
        start_col=start_col,
        end_col=end_col,
        text=" ".join(texts)[:500] if texts else None,
    )


def _rows_containing(rows: list[tuple[Any, ...]], tokens: tuple[str, ...]) -> list[int]:
    result: list[int] = []
    for idx, row in enumerate(rows, start=1):
        if _row_has_token(row, tokens):
            result.append(idx)
    return result


def _by_item_score(normalized: dict[str, FieldMapping]) -> int:
    fields = set(normalized)
    score = len(fields & _BY_ITEM_CORE_FIELDS)
    if "current_depreciation" in fields:
        score += 1
    if "audit_recalculated_depreciation" in fields:
        score += 1
    if "management_depreciation" in fields:
        score += 1
    if "depreciation_difference" in fields:
        score += 1
    if "conclusion" in fields:
        score += 1
    return score


def _sample_score(
    sheet_name: str,
    rows: list[tuple[Any, ...]],
    header_cells: list[tuple[int, str]],
) -> int:
    text = _combined_text(sheet_name, rows[:30])
    headers = " ".join(text for _, text in header_cells)
    score = 0
    for token in ("抽样", "样本", "选样", "sample", "凭证", "检查程序"):
        if token in text.lower() or token in headers.lower():
            score += 1
    return score


def _is_policy_review(
    sheet_name: str,
    rows: list[tuple[Any, ...]],
    kind: SheetKind,
) -> bool:
    if kind == SheetKind.DEPRECIATION_POLICY:
        return True
    text = _combined_text(sheet_name, rows[:20])
    return "K.03.3" in sheet_name or ("折旧政策" in text and "复核" in text)


def _is_sap_sheet(sheet_name: str, kind: SheetKind) -> bool:
    return kind == SheetKind.SAP or "K.03.1" in sheet_name or "SAP" in sheet_name.upper()


def _looks_like_k03_sheet(sheet_name: str) -> bool:
    normalized = sheet_name.replace(" ", "").upper()
    return "K.03" in normalized or "K03" in normalized


def _combined_text(sheet_name: str, rows: list[tuple[Any, ...]]) -> str:
    cells = [sheet_name]
    for row in rows:
        for value in row:
            text = _text(value)
            if text:
                cells.append(text)
    return " ".join(cells)


def _row_has_token(values: Any, tokens: tuple[str, ...]) -> bool:
    text = " ".join(_text(value) for value in values if _text(value))
    lower = text.lower()
    return any(token.lower() in lower for token in tokens)


def _is_blank(values: Any) -> bool:
    return not any(_text(value) for value in values)


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text).strip().lower())
