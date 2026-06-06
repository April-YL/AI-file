from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from ingest.records import FaListDataset
from ingest.sheet_loader import find_sheets_by_kind
from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from ingest.models import SheetKind
from ingest.workbook_reader import read_worksheet_rows


@dataclass
class AdditionTestSheetDataset:
    """K.02.1 新增测试页读取结果（第一阶段仅用于执行路径识别）。"""

    source_file: str
    source_sheet: str
    waiver_note_text: str | None = None
    waiver_note_rows: list[int] = field(default_factory=list)
    recognition_confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class AdditionSampleOutputDataset:
    """K.02.1a 新增选样输出页读取结果（第一阶段仅识别存在性）。"""

    source_file: str
    source_sheet: str
    recognition_confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class AdditionExecutionPathDataset:
    """K2-A 新增测试执行路径识别结果。"""

    path_kind: str
    recognition_confidence: float
    summary_status: str | None = None
    summary_waiver_reason: str | None = None
    summary_source_row: int | None = None
    addition_list_sheet: str | None = None
    addition_test_sheet: str | None = None
    addition_sample_output_sheet: str | None = None
    test_sheet_waiver_note: str | None = None
    test_sheet_waiver_rows: list[int] = field(default_factory=list)
    missing_components: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_kind": self.path_kind,
            "recognition_confidence": self.recognition_confidence,
            "summary_status": self.summary_status,
            "summary_waiver_reason": self.summary_waiver_reason,
            "summary_source_row": self.summary_source_row,
            "addition_list_sheet": self.addition_list_sheet,
            "addition_test_sheet": self.addition_test_sheet,
            "addition_sample_output_sheet": self.addition_sample_output_sheet,
            "test_sheet_waiver_note": self.test_sheet_waiver_note,
            "test_sheet_waiver_rows": self.test_sheet_waiver_rows,
            "missing_components": self.missing_components,
            "notes": self.notes,
        }


_WAIVER_TERMS = (
    "无新增",
    "本期无购置",
    "没有新增",
    "无需执行",
    "无需测试",
    "无需抽样",
    "不执行",
    "未执行",
    "小于te",
    "低于te",
    "小于tt",
    "低于tt",
    "无性质异常",
    "无异常性质",
)
_GUIDANCE_TERMS = (
    "基础操作指引",
    "进阶实操提示",
    "易错点",
    "canvas form",
    "sop",
    "审计抽样指南",
)


def load_addition_test_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 150,
) -> AdditionTestSheetDataset | None:
    path = Path(path)
    candidate = _choose_candidate(path, SheetKind.ADDITION_TEST, sheet_name, max_rows=max_rows)
    if candidate is None:
        return None
    rows = candidate["rows"]
    waiver_text, waiver_rows = _scan_waiver_notes(rows)
    notes = [f"addition_test_sheet_detected:{candidate['sheet_name']}"]
    if waiver_text:
        notes.append("addition_test_waiver_note_detected")
    return AdditionTestSheetDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        waiver_note_text=waiver_text,
        waiver_note_rows=waiver_rows,
        recognition_confidence=float(candidate["confidence"]),
        notes=notes,
    )


def load_addition_sample_output_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 150,
) -> AdditionSampleOutputDataset | None:
    path = Path(path)
    candidate = _choose_candidate(
        path, SheetKind.ADDITION_SAMPLE_OUTPUT, sheet_name, max_rows=max_rows
    )
    if candidate is None:
        return None
    return AdditionSampleOutputDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        recognition_confidence=float(candidate["confidence"]),
        notes=[f"addition_sample_output_sheet_detected:{candidate['sheet_name']}"],
    )


def build_addition_execution_path(
    *,
    summary: SummarySheetDataset | None,
    addition_list: FaListDataset | None,
    addition_test: AdditionTestSheetDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
) -> AdditionExecutionPathDataset:
    row = _find_summary_addition_row(summary)
    summary_status = _normalize_status(row.execution_status if row else None)
    summary_reason = _clean(row.waiver_reason if row else None)
    summary_source_row = row.source_row if row else None

    addition_list_sheet = _sheet_name(addition_list)
    addition_test_sheet = addition_test.source_sheet if addition_test else None
    sample_output_sheet = (
        addition_sample_output.source_sheet if addition_sample_output else None
    )
    missing = []
    if not addition_list_sheet:
        missing.append("新增清单")
    if not addition_test_sheet:
        missing.append("K.02.1 新增测试")
    if not sample_output_sheet:
        missing.append("K.02.1a 新增选样输出")

    notes: list[str] = []
    if row is None:
        notes.append("summary_addition_row_not_detected")
    if summary_status:
        notes.append(f"summary_status:{summary_status}")
    if missing:
        notes.append("missing_components:" + ",".join(missing))

    waiver_note = addition_test.waiver_note_text if addition_test else None
    waiver_rows = addition_test.waiver_note_rows if addition_test else []

    if summary_status == "no":
        path_kind = "summary_waived"
        confidence = 0.82 if summary_reason else 0.68
    elif waiver_note:
        path_kind = "test_sheet_waiver_note"
        confidence = 0.72
    elif summary_status == "yes" and not missing:
        path_kind = "executed_package_complete"
        confidence = 0.86
    elif summary_status == "yes" and missing:
        path_kind = "executed_package_incomplete"
        confidence = 0.76
    else:
        path_kind = "unclear"
        confidence = 0.45 if (addition_test_sheet or sample_output_sheet or addition_list_sheet) else 0.2

    return AdditionExecutionPathDataset(
        path_kind=path_kind,
        recognition_confidence=confidence,
        summary_status=summary_status,
        summary_waiver_reason=summary_reason,
        summary_source_row=summary_source_row,
        addition_list_sheet=addition_list_sheet,
        addition_test_sheet=addition_test_sheet,
        addition_sample_output_sheet=sample_output_sheet,
        test_sheet_waiver_note=waiver_note,
        test_sheet_waiver_rows=waiver_rows,
        missing_components=missing,
        notes=notes,
    )


def _choose_candidate(
    path: Path,
    kind: SheetKind,
    sheet_name: str | None,
    *,
    max_rows: int | None,
) -> dict[str, Any] | None:
    if sheet_name:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb[sheet_name]
            rows = read_worksheet_rows(ws, max_rows=max_rows)
        finally:
            wb.close()
        return {"sheet_name": sheet_name, "confidence": 0.9, "rows": rows}

    candidates = find_sheets_by_kind(path, kind, max_rows=max_rows or 150)
    if not candidates:
        return None
    chosen = candidates[0]
    return {
        "sheet_name": chosen.sheet_name,
        "confidence": chosen.confidence,
        "rows": chosen.rows,
    }


def _scan_waiver_notes(rows: list[tuple[Any, ...]]) -> tuple[str | None, list[int]]:
    hits: list[str] = []
    hit_rows: list[int] = []
    for r_idx, row in enumerate(rows, 1):
        # K.02.1 标准模板右侧是 SOP 指引列；先只扫左侧业务编制区，减少误识别。
        texts = [_clean(v) for v in row[:18]]
        joined = " ".join(t for t in texts if t)
        if not joined:
            continue
        low = _norm(joined)
        if any(term in low for term in _GUIDANCE_TERMS):
            continue
        if any(term in low for term in _WAIVER_TERMS):
            hits.append(_truncate(joined, 240))
            hit_rows.append(r_idx)
    if not hits:
        return None, []
    return "；".join(hits[:3]), hit_rows[:6]


def _find_summary_addition_row(
    summary: SummarySheetDataset | None,
) -> PspProgramRow | None:
    if summary is None:
        return None
    candidates = [row for row in summary.programs if _is_addition_program_row(row)]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (0 if r.execution_status else 1, r.source_row or 0))
    return candidates[0]


def _is_addition_program_row(row: PspProgramRow) -> bool:
    text = _norm(f"{row.procedure_name} {row.sheet_ref or ''}")
    if "k021a" in text or "k021b" in text:
        return False
    if "k021" in text:
        return True
    return "新增" in text and any(token in text for token in ("测试", "细节", "tod"))


def _normalize_status(value: str | None) -> str | None:
    text = _norm(value)
    if not text:
        return None
    if text in {"是", "yes", "y", "执行", "已执行"} or ("执行" in text and "不执行" not in text):
        return "yes"
    if text in {"否", "no", "n", "不执行", "未执行"} or "不执行" in text or "未执行" in text:
        return "no"
    return "unknown"


def _sheet_name(dataset: FaListDataset | None) -> str | None:
    if dataset is None or not dataset.source_sheet:
        return None
    return dataset.source_sheet


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).strip().lower())


def _truncate(value: str, max_len: int) -> str:
    return value if len(value) <= max_len else value[: max_len - 1] + "…"
