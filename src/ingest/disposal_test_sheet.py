from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import openpyxl

from ingest.models import SheetKind
from ingest.records import FaListDataset
from ingest.sheet_loader import find_sheets_by_kind
from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from ingest.workbook_reader import read_worksheet_rows


@dataclass
class DisposalAmountItem:
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
class DisposalParameterItem:
    label: str
    value: str | None
    source_row: int
    source_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "source_row": self.source_row,
            "source_column": self.source_column,
        }


@dataclass
class DisposalTestedSampleRow:
    source_row: int
    sample_type: str | None = None
    asset_category: str | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    sale_price: str | None = None
    disposal_voucher_no: str | None = None
    disposal_gain_loss: str | None = None
    support_sale_price: str | None = None
    sale_price_difference: str | None = None
    original_value: str | None = None
    accumulated_depreciation: str | None = None
    impairment_provision: str | None = None
    net_value: str | None = None
    disposal_date: str | None = None
    disposal_method: str | None = None
    evidence_amount: str | None = None
    evidence_description: str | None = None
    amount_difference: str | None = None
    attribute_results: list[str | None] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "sample_type": self.sample_type,
            "asset_category": self.asset_category,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "sale_price": self.sale_price,
            "disposal_voucher_no": self.disposal_voucher_no,
            "disposal_gain_loss": self.disposal_gain_loss,
            "support_sale_price": self.support_sale_price,
            "sale_price_difference": self.sale_price_difference,
            "original_value": self.original_value,
            "accumulated_depreciation": self.accumulated_depreciation,
            "impairment_provision": self.impairment_provision,
            "net_value": self.net_value,
            "disposal_date": self.disposal_date,
            "disposal_method": self.disposal_method,
            "evidence_amount": self.evidence_amount,
            "evidence_description": self.evidence_description,
            "amount_difference": self.amount_difference,
            "attribute_results": self.attribute_results,
        }


@dataclass
class DisposalSampleRow:
    source_row: int
    sample_type: str | None = None
    sample_source_no: str | None = None
    sampling_id: str | None = None
    asset_category: str | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    original_value: str | None = None
    accumulated_depreciation: str | None = None
    impairment_provision: str | None = None
    net_value: str | None = None
    disposal_date: str | None = None
    disposal_method: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "sample_type": self.sample_type,
            "sample_source_no": self.sample_source_no,
            "sampling_id": self.sampling_id,
            "asset_category": self.asset_category,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "original_value": self.original_value,
            "accumulated_depreciation": self.accumulated_depreciation,
            "impairment_provision": self.impairment_provision,
            "net_value": self.net_value,
            "disposal_date": self.disposal_date,
            "disposal_method": self.disposal_method,
        }


@dataclass
class DisposalTestSheetDataset:
    source_file: str
    source_sheet: str
    waiver_note_text: str | None = None
    waiver_note_rows: list[int] = field(default_factory=list)
    amounts: dict[str, DisposalAmountItem] = field(default_factory=dict)
    tested_samples: list[DisposalTestedSampleRow] = field(default_factory=list)
    recognition_confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class DisposalSampleOutputDataset:
    source_file: str
    source_sheet: str
    parameters: dict[str, DisposalParameterItem] = field(default_factory=dict)
    amounts: dict[str, DisposalAmountItem] = field(default_factory=dict)
    selected_samples: list[DisposalSampleRow] = field(default_factory=list)
    recognition_confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class DisposalExecutionPathDataset:
    path_kind: str
    recognition_confidence: float
    summary_status: str | None = None
    summary_waiver_reason: str | None = None
    summary_source_row: int | None = None
    disposal_list_sheet: str | None = None
    disposal_test_sheet: str | None = None
    disposal_sample_output_sheet: str | None = None
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
            "disposal_list_sheet": self.disposal_list_sheet,
            "disposal_test_sheet": self.disposal_test_sheet,
            "disposal_sample_output_sheet": self.disposal_sample_output_sheet,
            "test_sheet_waiver_note": self.test_sheet_waiver_note,
            "test_sheet_waiver_rows": self.test_sheet_waiver_rows,
            "missing_components": self.missing_components,
            "notes": self.notes,
        }


_AMOUNT_CHARS = re.compile(r"[¥$€,\s]")
_PAREN_NEGATIVE = re.compile(r"^\((.+)\)$")
_WAIVER_TERMS = (
    "无处置",
    "没有处置",
    "无需执行",
    "无需测试",
    "无需抽样",
    "不执行",
    "不再执行",
    "未执行",
    "未抽样",
    "小于te",
    "低于te",
    "小于tt",
    "低于tt",
    "小于sad",
    "低于sad",
    "净值小于",
    "处置资产净值小于",
    "无性质异常",
)
_GUIDANCE_TERMS = ("基础操作指引", "进阶实操提示", "易错点", "canvas form", "sop", "审计抽样指南")

_TEST_AMOUNT_ANCHORS: dict[str, tuple[str, ...]] = {
    "sale_scrap_net_value": (
        "出售报废净值",
        "出售+报废净值",
        "出售和报废净值",
        "处置/报废总金额",
        "处置报废总金额",
        "处置总金额",
        "处置测试总体",
        "样本总体金额",
    ),
    "sale_net_value": ("出售净值", "出售资产净值"),
    "scrap_net_value": ("报废净值", "报废资产净值"),
    "other_disposal_net_value": ("其他减少净值", "其他处置净值"),
    "rollforward_disposal_net_value": (
        "后推处置净值",
        "k01处置净值",
        "bkd处置净值",
        "breakdown中处置净值",
        "breakdown中处置/报废金额",
        "breakdown中处置报废金额",
        "breakdown中处置金额",
    ),
    "difference_amount": ("差异",),
    "key_item_amount": ("关键项目金额", "定量关键项目金额"),
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
_SAMPLE_PARAMETER_ANCHORS: dict[str, tuple[str, ...]] = {
    "te": ("可容忍误差", "TE", "Tolerable Error"),
    "covered_assertions": ("测试涵盖的认定", "涵盖的认定", "assertions covered"),
    "fraud_or_special_risk": ("舞弊或特别风险", "特别风险"),
    "cra": ("综合风险评估", "CRA", "Combined Risk Assessment"),
}


def load_disposal_test_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 150,
) -> DisposalTestSheetDataset | None:
    path = Path(path)
    candidate = _choose_candidate(path, SheetKind.DISPOSAL_TEST, sheet_name, max_rows=max_rows)
    if candidate is None:
        return None
    rows = candidate["rows"]
    waiver_text, waiver_rows = _scan_waiver_notes(rows)
    amounts = _extract_amount_items(rows, _TEST_AMOUNT_ANCHORS)
    tested_samples = _extract_tested_samples(rows)
    notes = [f"disposal_test_sheet_detected:{candidate['sheet_name']}"]
    if waiver_text:
        notes.append("disposal_test_waiver_note_detected")
    if amounts:
        notes.append(f"disposal_test_amounts_detected:{len(amounts)}")
    if tested_samples:
        notes.append(f"disposal_test_samples_detected:{len(tested_samples)}")
    return DisposalTestSheetDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        waiver_note_text=waiver_text,
        waiver_note_rows=waiver_rows,
        amounts=amounts,
        tested_samples=tested_samples,
        recognition_confidence=float(candidate["confidence"]),
        notes=notes,
    )


def load_disposal_sample_output_from_workbook(
    path: str | Path,
    *,
    sheet_name: str | None = None,
    max_rows: int | None = 150,
) -> DisposalSampleOutputDataset | None:
    path = Path(path)
    candidate = _choose_candidate(path, SheetKind.DISPOSAL_SAMPLE_OUTPUT, sheet_name, max_rows=max_rows)
    if candidate is None:
        return None
    rows = candidate["rows"]
    parameters = _extract_parameter_items(rows, _SAMPLE_PARAMETER_ANCHORS)
    amounts = _extract_amount_items(rows, _SAMPLE_AMOUNT_ANCHORS)
    selected_samples = _extract_selected_samples(rows)
    notes = [f"disposal_sample_output_sheet_detected:{candidate['sheet_name']}"]
    if parameters:
        notes.append(f"disposal_sample_output_parameters_detected:{len(parameters)}")
    if amounts:
        notes.append(f"disposal_sample_output_amounts_detected:{len(amounts)}")
    if selected_samples:
        notes.append(f"disposal_sample_output_rows_detected:{len(selected_samples)}")
    return DisposalSampleOutputDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        parameters=parameters,
        amounts=amounts,
        selected_samples=selected_samples,
        recognition_confidence=float(candidate["confidence"]),
        notes=notes,
    )


def build_disposal_execution_path(
    *,
    summary: SummarySheetDataset | None,
    disposal_list: FaListDataset | None,
    disposal_test: DisposalTestSheetDataset | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
) -> DisposalExecutionPathDataset:
    row = _find_summary_disposal_row(summary)
    summary_status = _normalize_status(row.execution_status if row else None)
    summary_reason = _clean(row.waiver_reason if row else None)
    summary_source_row = row.source_row if row else None

    disposal_list_sheet = _sheet_name(disposal_list)
    disposal_test_sheet = disposal_test.source_sheet if disposal_test else None
    sample_output_sheet = disposal_sample_output.source_sheet if disposal_sample_output else None

    missing: list[str] = []
    notes: list[str] = []
    if row is None:
        notes.append("summary_disposal_row_not_detected")
    if summary_status:
        notes.append(f"summary_status:{summary_status}")

    waiver_note = disposal_test.waiver_note_text if disposal_test else None
    waiver_rows = disposal_test.waiver_note_rows if disposal_test else []

    if summary_status not in {"no"} and not waiver_note:
        if not disposal_list_sheet:
            missing.append("处置清单")
        if not disposal_test_sheet:
            missing.append("K.02.2 处置测试")
        if not sample_output_sheet:
            missing.append("K.02.2a 处置选样输出")
        if missing:
            notes.append("missing_components:" + ",".join(missing))

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
        confidence = 0.45 if (disposal_list_sheet or disposal_test_sheet or sample_output_sheet) else 0.2

    return DisposalExecutionPathDataset(
        path_kind=path_kind,
        recognition_confidence=confidence,
        summary_status=summary_status,
        summary_waiver_reason=summary_reason,
        summary_source_row=summary_source_row,
        disposal_list_sheet=disposal_list_sheet,
        disposal_test_sheet=disposal_test_sheet,
        disposal_sample_output_sheet=sample_output_sheet,
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
    return {"sheet_name": chosen.sheet_name, "confidence": chosen.confidence, "rows": chosen.rows}


def _scan_waiver_notes(rows: list[tuple[Any, ...]]) -> tuple[str | None, list[int]]:
    hits: list[str] = []
    hit_rows: list[int] = []
    for r_idx, row in enumerate(rows, 1):
        texts = [_clean(v) for v in row[:18]]
        joined = " ".join(t for t in texts if t)
        if not joined:
            continue
        low = _norm(joined)
        if any(term in low for term in map(_norm, _GUIDANCE_TERMS)):
            continue
        if any(term in low for term in map(_norm, _WAIVER_TERMS)):
            hits.append(_truncate(joined, 240))
            hit_rows.append(r_idx)
    if not hits:
        return None, []
    return "；".join(hits[:3]), hit_rows[:6]


def _extract_parameter_items(
    rows: list[tuple[Any, ...]],
    anchors: dict[str, tuple[str, ...]],
    *,
    max_anchor_col: int = 18,
) -> dict[str, DisposalParameterItem]:
    found: dict[str, DisposalParameterItem] = {}
    for r_idx, row in enumerate(rows, 1):
        for c_idx, cell in enumerate(row[:max_anchor_col], 1):
            label = _clean(cell)
            if not label or len(label) > 160:
                continue
            normalized = _norm(label)
            if any(term in normalized for term in map(_norm, _GUIDANCE_TERMS)):
                continue
            for key, terms in anchors.items():
                if key in found or not any(_norm(term) in normalized for term in terms):
                    continue
                value, value_col = _first_value_to_right(row, c_idx, require_numeric=key == "te")
                if value is None:
                    continue
                found[key] = DisposalParameterItem(label, _stringify_cell(value), r_idx, value_col)
    return found


def _extract_amount_items(
    rows: list[tuple[Any, ...]],
    anchors: dict[str, tuple[str, ...]],
    *,
    max_anchor_col: int = 18,
) -> dict[str, DisposalAmountItem]:
    found: dict[str, DisposalAmountItem] = {}
    for r_idx, row in enumerate(rows, 1):
        for c_idx, cell in enumerate(row[:max_anchor_col], 1):
            label = _clean(cell)
            if not label or len(label) > 120:
                continue
            normalized = _norm(label)
            if any(term in normalized for term in map(_norm, _GUIDANCE_TERMS)):
                continue
            for key, terms in anchors.items():
                if key in found or not any(_norm(term) in normalized for term in terms):
                    continue
                value, value_col = _first_value_to_right(
                    row,
                    c_idx,
                    require_numeric=key != "sample_method",
                    require_short_text=key == "sample_method",
                )
                if value is None:
                    continue
                found[key] = DisposalAmountItem(label, _stringify_cell(value), r_idx, value_col)
    return found


def _first_value_to_right(
    row: tuple[Any, ...],
    label_col: int,
    *,
    require_numeric: bool = False,
    require_short_text: bool = False,
) -> tuple[Any | None, int | None]:
    for c_idx in range(label_col + 1, min(len(row), label_col + 9) + 1):
        if c_idx - 1 >= len(row):
            break
        value = row[c_idx - 1]
        if value is None or str(value).strip() == "":
            continue
        if require_numeric and _parse_amount(value) is None:
            continue
        text = str(value).strip()
        if len(text) > 120:
            continue
        if require_short_text and "\n" in text:
            continue
        return value, c_idx
    return None, None


def _extract_selected_samples(rows: list[tuple[Any, ...]]) -> list[DisposalSampleRow]:
    header_row, mapping = _find_table_header(
        rows,
        _sample_field_terms(include_evidence=False),
        required=("sample_source_no", "sampling_id", "sample_type", "net_value"),
    )
    if header_row is None:
        return []
    out: list[DisposalSampleRow] = []
    for r_idx, row in _iter_table_rows(rows, header_row + 1, mapping):
        out.append(
            DisposalSampleRow(
                source_row=r_idx,
                sample_type=_value_at(row, mapping.get("sample_type")),
                sample_source_no=_value_at(row, mapping.get("sample_source_no")),
                sampling_id=_value_at(row, mapping.get("sampling_id")),
                asset_category=_value_at(row, mapping.get("asset_category")),
                asset_id=_value_at(row, mapping.get("asset_id")),
                asset_name=_value_at(row, mapping.get("asset_name")),
                original_value=_value_at(row, mapping.get("original_value")),
                accumulated_depreciation=_value_at(row, mapping.get("accumulated_depreciation")),
                impairment_provision=_value_at(row, mapping.get("impairment_provision")),
                net_value=_value_at(row, mapping.get("net_value")),
                disposal_date=_value_at(row, mapping.get("disposal_date")),
                disposal_method=_value_at(row, mapping.get("disposal_method")),
            )
        )
    return out


def _extract_tested_samples(rows: list[tuple[Any, ...]]) -> list[DisposalTestedSampleRow]:
    header_row, mapping = _find_table_header(
        rows,
        _sample_field_terms(include_evidence=True),
        required=("asset_id", "asset_name", "net_value"),
    )
    if header_row is None:
        return []
    attribute_cols = [col for field, col in mapping.items() if field.startswith("attribute_")]
    out: list[DisposalTestedSampleRow] = []
    for r_idx, row in _iter_table_rows(rows, header_row + 1, mapping):
        sample = DisposalTestedSampleRow(
            source_row=r_idx,
            sample_type=_value_at(row, mapping.get("sample_type")),
            asset_category=_value_at(row, mapping.get("asset_category")),
            asset_id=_value_at(row, mapping.get("asset_id")),
            asset_name=_value_at(row, mapping.get("asset_name")),
            sale_price=_value_at(row, mapping.get("sale_price")),
            disposal_voucher_no=_value_at(row, mapping.get("disposal_voucher_no")),
            disposal_gain_loss=_value_at(row, mapping.get("disposal_gain_loss")),
            support_sale_price=_value_at(row, mapping.get("support_sale_price")),
            sale_price_difference=_value_at(row, mapping.get("sale_price_difference")),
            original_value=_value_at(row, mapping.get("original_value")),
            accumulated_depreciation=_value_at(row, mapping.get("accumulated_depreciation")),
            impairment_provision=_value_at(row, mapping.get("impairment_provision")),
            net_value=_value_at(row, mapping.get("net_value")),
            disposal_date=_value_at(row, mapping.get("disposal_date")),
            disposal_method=_value_at(row, mapping.get("disposal_method")),
            evidence_amount=(
                _value_at(row, mapping.get("evidence_amount"))
                or _value_at(row, mapping.get("support_sale_price"))
            ),
            evidence_description=_value_at(row, mapping.get("evidence_description")),
            amount_difference=_value_at(row, mapping.get("amount_difference")),
            attribute_results=[_value_at(row, col) for col in attribute_cols],
        )
        if _is_valid_sample_row(sample):
            out.append(sample)
    return out


def _sample_field_terms(*, include_evidence: bool) -> dict[str, tuple[str, ...]]:
    terms = {
        "sample_source_no": ("源样本#", "源样本号", "样本#"),
        "sampling_id": ("抽样id", "抽样ID", "随机抽样ID"),
        "sample_type": ("样本类型",),
        "asset_category": ("固定资产类别", "资产类别"),
        "asset_id": ("固定资产编号", "资产编号", "卡片编号", "卡片编码"),
        "asset_name": ("固定资产名称", "资产名称"),
        "sale_price": ("出售价格", "出售价", "处置售价"),
        "disposal_voucher_no": ("处置交易凭证号", "交易凭证号", "凭证号"),
        "disposal_gain_loss": ("处置损益", "处置收益", "处置亏损"),
        "support_sale_price": ("出售价格（通过审计证据/支持性文件取得）", "支持性文件取得", "通过审计证据", "支持性文件金额"),
        "sale_price_difference": ("出售价格差异", "售价差异"),
        "evidence_amount": ("出售价格（通过审计证据/支持性文件取得）", "支持性文件取得", "通过审计证据", "支持性文件金额"),
        "original_value": ("资产原价", "原值", "固定资产原值", "处置原值"),
        "accumulated_depreciation": ("累计折旧", "处置累计折旧", "减少累计折旧"),
        "impairment_provision": ("减值准备", "减值"),
        "net_value": ("净值", "处置净值", "账面净值", "账面价值"),
        "disposal_date": ("处置日期", "处置/报废日", "减少日期", "报废日期", "业务日期"),
        "disposal_method": ("减少方式", "处置方式", "处置情况", "报废方式", "变动方式"),
    }
    if include_evidence:
        terms.update(
            {
                "evidence_description": ("获得的证据", "支持的描述", "证据描述"),
                "amount_difference": ("金额差异", "净值差异", "差异"),
            }
        )
    return terms


def _is_valid_sample_row(row: DisposalTestedSampleRow) -> bool:
    if row.asset_id and row.asset_name and row.net_value:
        return True
    if row.net_value and (row.asset_id or row.asset_name):
        return True
    if (
        row.sale_price
        or row.disposal_voucher_no
        or row.disposal_gain_loss
        or row.support_sale_price
        or row.sale_price_difference
        or row.evidence_amount
    ) and (row.asset_id or row.asset_name or row.net_value):
        return True
    if row.attribute_results and any(v is not None for v in row.attribute_results):
        return True
    return False


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
        if key in {"asset_id", "asset_name", "net_value", "sample_source_no", "sampling_id", "sample_type"}
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
        joined = _norm(" ".join(str(v) for v in row if v is not None))
        if any(term in joined for term in map(_norm, _GUIDANCE_TERMS)):
            continue
        out.append((r_idx, row))
    return out


def _find_summary_disposal_row(summary: SummarySheetDataset | None) -> PspProgramRow | None:
    if summary is None:
        return None
    candidates = [row for row in summary.programs if _is_disposal_program_row(row)]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (0 if r.execution_status else 1, r.source_row or 0))
    return candidates[0]


def _is_disposal_program_row(row: PspProgramRow) -> bool:
    text = _norm(f"{row.procedure_name} {row.sheet_ref or ''}")
    if "k022a" in text or "k022b" in text:
        return False
    if "k022" in text:
        return True
    return any(token in text for token in ("处置", "减少", "报废")) and any(
        token in text for token in ("测试", "细节", "tod")
    )


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
        value = _normalize_decimal_amount(value)
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, (int, float)):
        dec = _normalize_decimal_amount(Decimal(str(value)))
        text = format(dec, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value).strip()


def _normalize_decimal_amount(value: Decimal) -> Decimal:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(value - rounded) <= Decimal("0.000001"):
        return rounded
    return value


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
