from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import openpyxl

from ingest.records import FaListDataset
from ingest.sheet_loader import find_sheets_by_kind
from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from ingest.models import SheetKind
from ingest.workbook_reader import read_worksheet_rows


@dataclass
class AdditionAmountItem:
    label: str
    amount: str | None
    source_row: int
    source_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "amount": self.amount,
            "source_row": self.source_row,
            "source_column": self.source_column,
        }


@dataclass
class AdditionSampleRow:
    source_row: int
    sample_type: str | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    original_value: str | None = None
    addition_method: str | None = None
    sample_source_no: str | None = None
    sampling_id: str | None = None
    asset_category: str | None = None
    start_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "sample_type": self.sample_type,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "original_value": self.original_value,
            "addition_method": self.addition_method,
            "sample_source_no": self.sample_source_no,
            "sampling_id": self.sampling_id,
            "asset_category": self.asset_category,
            "start_date": self.start_date,
        }


@dataclass
class AdditionTestedSampleRow:
    source_row: int
    sample_type: str | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    original_value: str | None = None
    evidence_amount: str | None = None
    evidence_description: str | None = None
    amount_difference: str | None = None
    attribute_results: list[str | None] = field(default_factory=list)
    asset_category: str | None = None
    capitalized_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "sample_type": self.sample_type,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "original_value": self.original_value,
            "evidence_amount": self.evidence_amount,
            "evidence_description": self.evidence_description,
            "amount_difference": self.amount_difference,
            "attribute_results": self.attribute_results,
            "asset_category": self.asset_category,
            "capitalized_date": self.capitalized_date,
        }


@dataclass
class AdditionTestSheetDataset:
    """K.02.1 新增测试页读取结果。"""

    source_file: str
    source_sheet: str
    waiver_note_text: str | None = None
    waiver_note_rows: list[int] = field(default_factory=list)
    amounts: dict[str, AdditionAmountItem] = field(default_factory=dict)
    tested_samples: list[AdditionTestedSampleRow] = field(default_factory=list)
    recognition_confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class AdditionSampleOutputDataset:
    """K.02.1a 新增选样输出页读取结果。"""

    source_file: str
    source_sheet: str
    amounts: dict[str, AdditionAmountItem] = field(default_factory=dict)
    selected_samples: list[AdditionSampleRow] = field(default_factory=list)
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

_AMOUNT_CHARS = re.compile(r"[¥$€￥,\s]")
_PAREN_NEGATIVE = re.compile(r"^\((.+)\)$")

_TEST_AMOUNT_ANCHORS: dict[str, tuple[str, ...]] = {
    "purchase_population_amount": ("购置总金额", "购置新增总金额", "购置新增原值", "样本总体金额"),
    "rollforward_purchase_amount": ("breakdown中购置金额", "后推购置金额", "k01购置金额", "bkd购置金额"),
    "difference_amount": ("差异",),
    "key_item_amount": ("测试的关键项目", "关键项目金额"),
    "remaining_population_amount": ("代表性抽样的剩余总体", "剩余总体", "代表性总体"),
}
_SAMPLE_AMOUNT_ANCHORS: dict[str, tuple[str, ...]] = {
    "uploaded_data_amount": ("已上传数据", "上传数据"),
    "necessary_exclusion_amount": ("必要的数据排除项", "剔除项金额"),
    "sample_pool_amount": ("样本池总体金额", "样本池总金额"),
    "representative_population_amount": ("代表性总体价值", "代表性总体金额"),
    "total_amount": ("总金额",),
    "accounting_record_amount": ("会计记录的重大账户余额或活动", "会计记录金额"),
    "difference_amount": ("差额", "差异"),
    "key_item_count": ("关键项数量",),
    "key_item_amount": ("定量关键项金额", "关键项金额"),
    "representative_sample_size": ("代表性样本量",),
    "total_sample_size": ("代表性样本与关键项数量合计", "样本合计"),
    "sample_method": ("样本选择方法", "抽样方法"),
}


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
    amounts = _extract_amount_items(rows, _TEST_AMOUNT_ANCHORS)
    tested_samples = _extract_tested_samples(rows)
    notes = [f"addition_test_sheet_detected:{candidate['sheet_name']}"]
    if waiver_text:
        notes.append("addition_test_waiver_note_detected")
    if amounts:
        notes.append(f"addition_test_amounts_detected:{len(amounts)}")
    if tested_samples:
        notes.append(f"addition_test_samples_detected:{len(tested_samples)}")
    return AdditionTestSheetDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        waiver_note_text=waiver_text,
        waiver_note_rows=waiver_rows,
        amounts=amounts,
        tested_samples=tested_samples,
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
    rows = candidate["rows"]
    amounts = _extract_amount_items(rows, _SAMPLE_AMOUNT_ANCHORS)
    selected_samples = _extract_selected_samples(rows)
    notes = [f"addition_sample_output_sheet_detected:{candidate['sheet_name']}"]
    if amounts:
        notes.append(f"addition_sample_output_amounts_detected:{len(amounts)}")
    if selected_samples:
        notes.append(f"addition_sample_output_rows_detected:{len(selected_samples)}")
    return AdditionSampleOutputDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        amounts=amounts,
        selected_samples=selected_samples,
        recognition_confidence=float(candidate["confidence"]),
        notes=notes,
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


def _extract_amount_items(
    rows: list[tuple[Any, ...]],
    anchors: dict[str, tuple[str, ...]],
) -> dict[str, AdditionAmountItem]:
    found: dict[str, AdditionAmountItem] = {}
    for r_idx, row in enumerate(rows, 1):
        for c_idx, cell in enumerate(row, 1):
            label = _clean(cell)
            if not label:
                continue
            normalized = _norm(label)
            for key, terms in anchors.items():
                if key in found:
                    continue
                if not any(_norm(term) in normalized for term in terms):
                    continue
                value, value_col = _first_value_to_right(row, c_idx)
                if value is None:
                    continue
                found[key] = AdditionAmountItem(
                    label=label,
                    amount=_stringify_cell(value),
                    source_row=r_idx,
                    source_column=value_col,
                )
    return found


def _first_value_to_right(row: tuple[Any, ...], label_col: int) -> tuple[Any | None, int | None]:
    for c_idx in range(label_col + 1, min(len(row), label_col + 9) + 1):
        if c_idx - 1 >= len(row):
            break
        value = row[c_idx - 1]
        if value is None or str(value).strip() == "":
            continue
        # 说明性长文本不是金额/数量/方法摘录的首选值。
        text = str(value).strip()
        if len(text) > 120:
            continue
        return value, c_idx
    return None, None


def _extract_selected_samples(rows: list[tuple[Any, ...]]) -> list[AdditionSampleRow]:
    header_row, mapping = _find_table_header(
        rows,
        {
            "sample_source_no": ("源样本#", "源样本号", "样本#"),
            "sampling_id": ("抽样id", "抽样ID", "随机抽样ID"),
            "sample_type": ("样本类型",),
            "asset_category": ("固定资产类别", "资产类别"),
            "asset_id": ("固定资产编号", "资产编号", "卡片编号"),
            "asset_name": ("固定资产名称", "资产名称"),
            "start_date": ("入账开始日期", "资本化日期"),
            "original_value": ("原值", "资产原价", "固定资产原值"),
            "addition_method": ("新增方式", "增加方式", "取得方式"),
        },
        required=("asset_id", "asset_name", "original_value"),
    )
    if header_row is None:
        return []
    out: list[AdditionSampleRow] = []
    for r_idx, row in _iter_table_rows(rows, header_row + 1, mapping):
        out.append(
            AdditionSampleRow(
                source_row=r_idx,
                sample_type=_value_at(row, mapping.get("sample_type")),
                asset_id=_value_at(row, mapping.get("asset_id")),
                asset_name=_value_at(row, mapping.get("asset_name")),
                original_value=_value_at(row, mapping.get("original_value")),
                addition_method=_value_at(row, mapping.get("addition_method")),
                sample_source_no=_value_at(row, mapping.get("sample_source_no")),
                sampling_id=_value_at(row, mapping.get("sampling_id")),
                asset_category=_value_at(row, mapping.get("asset_category")),
                start_date=_value_at(row, mapping.get("start_date")),
            )
        )
    return out


def _extract_tested_samples(rows: list[tuple[Any, ...]]) -> list[AdditionTestedSampleRow]:
    header_row, mapping = _find_table_header(
        rows,
        {
            "sample_type": ("样本类型",),
            "asset_category": ("固定资产类别", "资产类别"),
            "asset_id": ("固定资产编号", "资产编号", "卡片编号"),
            "asset_name": ("固定资产名称", "资产名称"),
            "original_value": ("资产原价", "原值", "固定资产原值"),
            "capitalized_date": ("资本化日期", "入账开始日期"),
            "evidence_amount": ("支持性文件取得", "通过审计证据", "支持性文件金额"),
            "evidence_description": ("获得的证据", "支持的描述", "证据描述"),
            "amount_difference": ("资产原价差异", "金额差异", "差异"),
        },
        required=("asset_id", "asset_name", "original_value"),
    )
    if header_row is None:
        return []
    attribute_cols = [
        col
        for field, col in mapping.items()
        if field.startswith("attribute_")
    ]
    out: list[AdditionTestedSampleRow] = []
    for r_idx, row in _iter_table_rows(rows, header_row + 1, mapping):
        out.append(
            AdditionTestedSampleRow(
                source_row=r_idx,
                sample_type=_value_at(row, mapping.get("sample_type")),
                asset_id=_value_at(row, mapping.get("asset_id")),
                asset_name=_value_at(row, mapping.get("asset_name")),
                original_value=_value_at(row, mapping.get("original_value")),
                evidence_amount=_value_at(row, mapping.get("evidence_amount")),
                evidence_description=_value_at(row, mapping.get("evidence_description")),
                amount_difference=_value_at(row, mapping.get("amount_difference")),
                attribute_results=[_value_at(row, col) for col in attribute_cols],
                asset_category=_value_at(row, mapping.get("asset_category")),
                capitalized_date=_value_at(row, mapping.get("capitalized_date")),
            )
        )
    return out


def _find_table_header(
    rows: list[tuple[Any, ...]],
    field_terms: dict[str, tuple[str, ...]],
    *,
    required: tuple[str, ...],
) -> tuple[int | None, dict[str, int]]:
    best_row: int | None = None
    best_mapping: dict[str, int] = {}
    best_score = 0
    for r_idx, row in enumerate(rows, 1):
        mapping: dict[str, int] = {}
        for c_idx, cell in enumerate(row, 1):
            text = _norm(cell)
            if not text:
                continue
            matched = False
            for field, terms in field_terms.items():
                if field in mapping:
                    continue
                if any(_norm(term) == text or _norm(term) in text for term in terms):
                    mapping[field] = c_idx
                    matched = True
                    break
            if not matched and text in {"1", "2", "3", "4"}:
                mapping[f"attribute_{text}"] = c_idx
        score = len(mapping)
        if score > best_score and all(field in mapping for field in required):
            best_score = score
            best_row = r_idx
            best_mapping = mapping
    return best_row, best_mapping


def _iter_table_rows(
    rows: list[tuple[Any, ...]],
    start_row: int,
    mapping: dict[str, int],
) -> list[tuple[int, tuple[Any, ...]]]:
    out: list[tuple[int, tuple[Any, ...]]] = []
    blank_streak = 0
    identity_cols = [
        col
        for key, col in mapping.items()
        if key in {"asset_id", "asset_name", "original_value"}
    ]
    for r_idx in range(start_row, len(rows) + 1):
        row = rows[r_idx - 1]
        has_identity = any(_value_at(row, col) for col in identity_cols)
        if not has_identity:
            blank_streak += 1
            if blank_streak >= 2:
                break
            continue
        blank_streak = 0
        # 避免把说明段落误当作样本行。
        joined = _norm(" ".join(str(v) for v in row if v is not None))
        if any(term in joined for term in _GUIDANCE_TERMS):
            continue
        out.append((r_idx, row))
    return out


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


def _stringify_cell(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
    if isinstance(value, (int, float)):
        dec = Decimal(str(value))
        text = format(dec, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value).strip()


def _parse_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in ("-", "—", "N/A", "n/a", "#N/A"):
        return None
    text = _AMOUNT_CHARS.sub("", text)
    paren = _PAREN_NEGATIVE.match(text)
    if paren:
        text = f"-{paren.group(1)}"
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _value_at(row: tuple[Any, ...], col: int | None) -> str | None:
    if col is None or col <= 0 or col > len(row):
        return None
    value = row[col - 1]
    if value is None or str(value).strip() == "":
        return None
    amount = _parse_amount(value)
    if amount is not None:
        return str(amount)
    return str(value).strip()


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).strip().lower())


def _truncate(value: str, max_len: int) -> str:
    return value if len(value) <= max_len else value[: max_len - 1] + "…"
