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
class AdditionParameterItem:
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
    useful_life_months: str | None = None
    salvage_rate: str | None = None

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
            "useful_life_months": self.useful_life_months,
            "salvage_rate": self.salvage_rate,
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
    gl_account_code: str | None = None
    capitalized_date: str | None = None
    useful_life_months: str | None = None
    salvage_rate: str | None = None
    depreciation_method: str | None = None

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
            "gl_account_code": self.gl_account_code,
            "capitalized_date": self.capitalized_date,
            "useful_life_months": self.useful_life_months,
            "salvage_rate": self.salvage_rate,
            "depreciation_method": self.depreciation_method,
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
    module_assessments: list[ModuleAssessment] = field(default_factory=list)
    recognition_confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class AdditionSampleOutputDataset:
    """K.02.1a 新增选样输出页读取结果。"""

    source_file: str
    source_sheet: str
    parameters: dict[str, AdditionParameterItem] = field(default_factory=dict)
    amounts: dict[str, AdditionAmountItem] = field(default_factory=dict)
    selected_samples: list[AdditionSampleRow] = field(default_factory=list)
    module_assessments: list[ModuleAssessment] = field(default_factory=list)
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


@dataclass
class ModuleAssessment:
    module_key: str
    module_name: str
    status: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_key": self.module_key,
            "module_name": self.module_name,
            "status": self.status,
            "confidence": self.confidence,
            "evidence": self.evidence,
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
    "不在执行",
    "不再执行",
    "不执行tod",
    "不在执行tod",
    "不再执行tod",
    "未执行",
    "小于te",
    "低于te",
    "小于tt",
    "低于tt",
    "小于sad",
    "低于sad",
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
_SAMPLE_PARAMETER_ANCHORS: dict[str, tuple[str, ...]] = {
    "te": ("可容忍误差", "TE", "Tolerable Error"),
    "covered_assertions": ("测试涵盖的认定", "涵盖的认定", "assertions covered"),
    "fraud_or_special_risk": ("是否存在与上述认定相关的舞弊或特别风险", "舞弊或特别风险"),
    "cra": ("综合风险评估", "CRA", "Combined Risk Assessment"),
}


def _build_module_assessments(
    rows: list[tuple[Any, ...]],
    *,
    execution_path: AdditionExecutionPathDataset,
    waiver_text: str | None,
    amounts: dict[str, AdditionAmountItem],
    tested_samples: list[AdditionTestedSampleRow],
) -> list[ModuleAssessment]:
    return [
        _assess_execution_path(execution_path),
        _assess_population_definition(rows, amounts),
        _assess_amount_reconciliation(amounts),
        _assess_key_item_and_representation(rows, amounts),
        _assess_test_sample_table(tested_samples),
        _assess_exception_summary(rows, waiver_text, tested_samples),
    ]


def _assess_execution_path(execution_path: AdditionExecutionPathDataset) -> ModuleAssessment:
    evidence = [f"path_kind={execution_path.path_kind}"]
    if execution_path.summary_status:
        evidence.append(f"summary_status={execution_path.summary_status}")
    if execution_path.summary_waiver_reason:
        evidence.append(f"summary_reason={execution_path.summary_waiver_reason}")
    if execution_path.test_sheet_waiver_note:
        evidence.append("test_sheet_waiver_note")
    if execution_path.missing_components:
        evidence.append("missing=" + ",".join(execution_path.missing_components))
    if execution_path.path_kind in {
        "summary_waived",
        "executed_package_complete",
        "test_sheet_waiver_note",
    }:
        status = "recognized"
    elif execution_path.path_kind in {"executed_package_incomplete"}:
        status = "partial"
    else:
        status = "unclear"
    return ModuleAssessment(
        module_key="execution_path",
        module_name="执行路径",
        status=status,
        confidence=execution_path.recognition_confidence,
        evidence=evidence,
        notes=list(execution_path.notes),
    )


def _assess_population_definition(
    rows: list[tuple[Any, ...]],
    amounts: dict[str, AdditionAmountItem],
) -> ModuleAssessment:
    hits = _collect_text_hits(
        rows,
        (
            "详细测试所涵盖的总体",
            "样本总体",
            "购置增加",
            "购置新增",
            "本年固定资产购置增加",
            "测试总体",
        ),
    )
    purchase_amount = amounts.get("purchase_population_amount")
    rollforward_amount = amounts.get("rollforward_purchase_amount")
    evidence = hits[:4]
    if purchase_amount:
        evidence.append(f"purchase_population_amount={purchase_amount.amount}")
    if rollforward_amount:
        evidence.append(f"rollforward_purchase_amount={rollforward_amount.amount}")
    if purchase_amount and hits:
        status = "recognized"
    elif purchase_amount or hits:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="population_definition",
        module_name="新增测试总体定义",
        status=status,
        confidence=0.78 if hits else 0.52 if purchase_amount else 0.25,
        evidence=evidence,
        notes=[],
    )


def _assess_amount_reconciliation(
    amounts: dict[str, AdditionAmountItem],
) -> ModuleAssessment:
    purchase = _amount_decimal(amounts.get("purchase_population_amount"))
    rollforward = _amount_decimal(amounts.get("rollforward_purchase_amount"))
    diff = _amount_decimal(amounts.get("difference_amount"))
    evidence: list[str] = []
    for key in ("purchase_population_amount", "rollforward_purchase_amount", "difference_amount"):
        item = amounts.get(key)
        if item and item.amount is not None:
            evidence.append(f"{key}={item.amount}")
    if purchase is not None and rollforward is not None and diff is not None:
        status = "recognized" if diff == purchase - rollforward and diff == 0 else "partial"
    elif purchase is not None or rollforward is not None:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="amount_reconciliation",
        module_name="金额勾稽",
        status=status,
        confidence=0.88 if status == "recognized" else 0.64 if status == "partial" else 0.3,
        evidence=evidence,
        notes=[],
    )


def _assess_key_item_and_representation(
    rows: list[tuple[Any, ...]],
    amounts: dict[str, AdditionAmountItem],
) -> ModuleAssessment:
    hits = _collect_text_hits(
        rows,
        (
            "关键项目",
            "代表性样本",
            "关键项",
            "定量关键项",
            "定性关键项",
            "Skywind",
            "Smart Sampling",
            "抽样工具",
            "TT",
        ),
    )
    evidence = hits[:4]
    for key in (
        "key_item_amount",
        "key_item_count",
        "representative_sample_size",
        "total_sample_size",
        "sample_method",
    ):
        item = amounts.get(key)
        if item and item.amount is not None:
            evidence.append(f"{key}={item.amount}")
    if amounts.get("key_item_amount") or amounts.get("representative_sample_size"):
        status = "recognized"
    elif hits:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="key_item_representation",
        module_name="关键项目与代表性抽样",
        status=status,
        confidence=0.74 if hits else 0.38,
        evidence=evidence,
        notes=[],
    )


def _assess_test_sample_table(
    tested_samples: list[AdditionTestedSampleRow],
) -> ModuleAssessment:
    evidence: list[str] = [f"tested_samples={len(tested_samples)}"]
    if tested_samples:
        first = tested_samples[0]
        evidence.append(f"first_asset_id={first.asset_id or ''}")
        evidence.append(f"first_asset_name={first.asset_name or ''}")
        evidence.append(f"attribute_count={len([v for v in first.attribute_results if v is not None])}")
    if tested_samples and all(s.asset_id and s.asset_name and s.original_value for s in tested_samples):
        if any(s.attribute_results for s in tested_samples):
            status = "recognized"
        else:
            status = "partial"
    elif tested_samples:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="sample_table",
        module_name="测试样本与属性表",
        status=status,
        confidence=0.86 if status == "recognized" else 0.6 if status == "partial" else 0.25,
        evidence=evidence,
        notes=[],
    )


def _assess_exception_summary(
    rows: list[tuple[Any, ...]],
    waiver_text: str | None,
    tested_samples: list[AdditionTestedSampleRow],
) -> ModuleAssessment:
    hits = _collect_text_hits(rows, ("无异常情况", "已识别异常", "异常情况", "Note", "说明", "调查"))
    evidence = hits[:4]
    if waiver_text:
        evidence.append(f"waiver_text={waiver_text}")
    if tested_samples:
        any_note = any(
            (s.evidence_description and _norm(s.evidence_description).find("异常") >= 0)
            or (s.amount_difference and _norm(s.amount_difference).strip() not in {"", "0"})
            for s in tested_samples
        )
        if any_note:
            evidence.append("sample_level_exception_or_difference")
    if waiver_text or any("无异常" in hit for hit in hits):
        status = "recognized"
    elif hits:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="exception_summary",
        module_name="异常说明与结论",
        status=status,
        confidence=0.72 if waiver_text else 0.58 if hits else 0.28,
        evidence=evidence,
        notes=[],
    )


def _collect_text_hits(
    rows: list[tuple[Any, ...]],
    terms: tuple[str, ...],
    *,
    max_cols: int = 24,
    limit: int = 6,
) -> list[str]:
    hits: list[str] = []
    for row in rows:
        texts = [_clean(v) for v in row[:max_cols]]
        joined = " ".join(t for t in texts if t)
        if not joined:
            continue
        low = _norm(joined)
        if any(term in low for term in map(_norm, terms)):
            hits.append(_truncate(joined, 200))
            if len(hits) >= limit:
                break
    return hits


def _amount_decimal(item: AdditionAmountItem | None) -> Decimal | None:
    if item is None or item.amount is None:
        return None
    return _parse_amount(item.amount)


def _build_sample_output_module_assessments(
    rows: list[tuple[Any, ...]],
    *,
    parameters: dict[str, AdditionParameterItem],
    amounts: dict[str, AdditionAmountItem],
    selected_samples: list[AdditionSampleRow],
) -> list[ModuleAssessment]:
    return [
        _assess_sample_prerequisites(parameters),
        _assess_sample_source_summary(rows, amounts),
        _assess_sample_strategy(rows, amounts),
        _assess_sample_accounting_reconciliation(amounts),
        _assess_selected_sample_table(selected_samples),
    ]


def _assess_sample_prerequisites(
    parameters: dict[str, AdditionParameterItem],
) -> ModuleAssessment:
    evidence: list[str] = []
    for key in ("te", "covered_assertions", "fraud_or_special_risk", "cra"):
        item = parameters.get(key)
        if item and item.value is not None:
            evidence.append(f"{key}={item.value}")
    if all(key in parameters for key in ("te", "covered_assertions", "cra")):
        status = "recognized"
    elif evidence:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="sampling_prerequisites",
        module_name="抽样参数与测试认定",
        status=status,
        confidence=0.86 if status == "recognized" else 0.58 if status == "partial" else 0.25,
        evidence=evidence,
        notes=[],
    )


def _assess_sample_source_summary(
    rows: list[tuple[Any, ...]],
    amounts: dict[str, AdditionAmountItem],
) -> ModuleAssessment:
    hits = _collect_text_hits(rows, ("源数据汇总", "已上传数据", "样本池总体金额"), max_cols=12)
    evidence = hits[:3]
    for key in ("uploaded_data_amount", "necessary_exclusion_amount", "sample_pool_amount"):
        item = amounts.get(key)
        if item and item.amount is not None:
            evidence.append(f"{key}={item.amount}")
    if amounts.get("uploaded_data_amount") and amounts.get("sample_pool_amount"):
        status = "recognized"
    elif hits or amounts:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="source_data_summary",
        module_name="源数据与样本池摘要",
        status=status,
        confidence=0.86 if status == "recognized" else 0.58 if status == "partial" else 0.25,
        evidence=evidence,
        notes=[],
    )


def _assess_sample_strategy(
    rows: list[tuple[Any, ...]],
    amounts: dict[str, AdditionAmountItem],
) -> ModuleAssessment:
    hits = _collect_text_hits(
        rows,
        ("抽样策略", "关键项数量", "代表性样本量", "样本选择方法", "随机抽样", "MUS"),
        max_cols=12,
    )
    evidence = hits[:4]
    for key in (
        "key_item_count",
        "key_item_amount",
        "representative_population_amount",
        "representative_sample_size",
        "total_sample_size",
        "sample_method",
    ):
        item = amounts.get(key)
        if item and item.amount is not None:
            evidence.append(f"{key}={item.amount}")
    if amounts.get("sample_method") and (
        amounts.get("representative_sample_size") or amounts.get("total_sample_size")
    ):
        status = "recognized"
    elif hits or any(key in amounts for key in ("sample_method", "representative_sample_size")):
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="sampling_strategy",
        module_name="抽样策略与样本量",
        status=status,
        confidence=0.84 if status == "recognized" else 0.56 if status == "partial" else 0.25,
        evidence=evidence,
        notes=[],
    )


def _assess_sample_accounting_reconciliation(
    amounts: dict[str, AdditionAmountItem],
) -> ModuleAssessment:
    total = _amount_decimal(amounts.get("total_amount"))
    accounting = _amount_decimal(amounts.get("accounting_record_amount"))
    diff = _amount_decimal(amounts.get("difference_amount"))
    evidence: list[str] = []
    for key in ("total_amount", "accounting_record_amount", "difference_amount"):
        item = amounts.get(key)
        if item and item.amount is not None:
            evidence.append(f"{key}={item.amount}")
    if total is not None and accounting is not None and diff is not None:
        status = "recognized" if diff == total - accounting else "partial"
    elif total is not None or accounting is not None:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="accounting_reconciliation",
        module_name="总体与会计记录核对",
        status=status,
        confidence=0.86 if status == "recognized" else 0.58 if status == "partial" else 0.25,
        evidence=evidence,
        notes=[],
    )


def _assess_selected_sample_table(
    selected_samples: list[AdditionSampleRow],
) -> ModuleAssessment:
    evidence: list[str] = [f"selected_samples={len(selected_samples)}"]
    if selected_samples:
        first = selected_samples[0]
        evidence.append(f"first_sample_source_no={first.sample_source_no or ''}")
        evidence.append(f"first_sampling_id={first.sampling_id or ''}")
        evidence.append(f"first_asset_id={first.asset_id or ''}")
    if selected_samples and all(
        row.sample_source_no and row.sampling_id and row.sample_type and row.asset_id and row.original_value
        for row in selected_samples
    ):
        status = "recognized"
    elif selected_samples:
        status = "partial"
    else:
        status = "missing"
    return ModuleAssessment(
        module_key="selected_samples",
        module_name="已选取样本明细",
        status=status,
        confidence=0.9 if status == "recognized" else 0.6 if status == "partial" else 0.25,
        evidence=evidence,
        notes=[],
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
    amounts = _extract_amount_items(rows, _TEST_AMOUNT_ANCHORS)
    tested_samples = _extract_tested_samples(rows)
    if waiver_text:
        path_kind = "test_sheet_waiver_note"
        path_confidence = 0.72
    elif amounts and tested_samples:
        path_kind = "executed_package_complete"
        path_confidence = 0.84
    elif amounts or tested_samples:
        path_kind = "executed_package_incomplete"
        path_confidence = 0.63
    else:
        path_kind = "unclear"
        path_confidence = 0.35
    module_assessments = _build_module_assessments(
        rows,
        execution_path=AdditionExecutionPathDataset(
            path_kind=path_kind,
            recognition_confidence=path_confidence,
            test_sheet_waiver_note=waiver_text,
            test_sheet_waiver_rows=waiver_rows,
            notes=["page_only_execution_path_inferred"],
        ),
        waiver_text=waiver_text,
        amounts=amounts,
        tested_samples=tested_samples,
    )
    notes = [f"addition_test_sheet_detected:{candidate['sheet_name']}"]
    if waiver_text:
        notes.append("addition_test_waiver_note_detected")
    if amounts:
        notes.append(f"addition_test_amounts_detected:{len(amounts)}")
    if tested_samples:
        notes.append(f"addition_test_samples_detected:{len(tested_samples)}")
    if module_assessments:
        notes.append(f"addition_test_modules_detected:{len(module_assessments)}")
    return AdditionTestSheetDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        waiver_note_text=waiver_text,
        waiver_note_rows=waiver_rows,
        amounts=amounts,
        tested_samples=tested_samples,
        module_assessments=module_assessments,
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
    parameters = _extract_parameter_items(rows, _SAMPLE_PARAMETER_ANCHORS)
    amounts = _extract_amount_items(rows, _SAMPLE_AMOUNT_ANCHORS)
    selected_samples = _extract_selected_samples(rows)
    module_assessments = _build_sample_output_module_assessments(
        rows,
        parameters=parameters,
        amounts=amounts,
        selected_samples=selected_samples,
    )
    notes = [f"addition_sample_output_sheet_detected:{candidate['sheet_name']}"]
    if parameters:
        notes.append(f"addition_sample_output_parameters_detected:{len(parameters)}")
    if amounts:
        notes.append(f"addition_sample_output_amounts_detected:{len(amounts)}")
    if selected_samples:
        notes.append(f"addition_sample_output_rows_detected:{len(selected_samples)}")
    if module_assessments:
        notes.append(f"addition_sample_output_modules_detected:{len(module_assessments)}")
    return AdditionSampleOutputDataset(
        source_file=str(path),
        source_sheet=candidate["sheet_name"],
        parameters=parameters,
        amounts=amounts,
        selected_samples=selected_samples,
        module_assessments=module_assessments,
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


def _extract_parameter_items(
    rows: list[tuple[Any, ...]],
    anchors: dict[str, tuple[str, ...]],
    *,
    max_anchor_col: int = 18,
) -> dict[str, AdditionParameterItem]:
    found: dict[str, AdditionParameterItem] = {}
    for r_idx, row in enumerate(rows, 1):
        for c_idx, cell in enumerate(row[:max_anchor_col], 1):
            label = _clean(cell)
            if not label:
                continue
            normalized = _norm(label)
            if len(label) > 160:
                continue
            if any(term in normalized for term in _GUIDANCE_TERMS):
                continue
            for key, terms in anchors.items():
                if key in found:
                    continue
                if not any(_norm(term) in normalized for term in terms):
                    continue
                value, value_col = _first_value_to_right(
                    row,
                    c_idx,
                    require_numeric=key == "te",
                    require_short_text=key != "te",
                )
                if value is None:
                    continue
                found[key] = AdditionParameterItem(
                    label=label,
                    value=_stringify_cell(value),
                    source_row=r_idx,
                    source_column=value_col,
                )
    return found


def _extract_amount_items(
    rows: list[tuple[Any, ...]],
    anchors: dict[str, tuple[str, ...]],
    *,
    max_anchor_col: int = 18,
) -> dict[str, AdditionAmountItem]:
    found: dict[str, AdditionAmountItem] = {}
    for r_idx, row in enumerate(rows, 1):
        for c_idx, cell in enumerate(row[:max_anchor_col], 1):
            label = _clean(cell)
            if not label:
                continue
            normalized = _norm(label)
            if len(label) > 120:
                continue
            if any(term in normalized for term in _GUIDANCE_TERMS):
                continue
            for key, terms in anchors.items():
                if key in found:
                    continue
                if not any(_norm(term) in normalized for term in terms):
                    continue
                value, value_col = _first_value_to_right(
                    row,
                    c_idx,
                    require_numeric=_amount_item_requires_numeric(key),
                    require_short_text=key == "sample_method",
                )
                if value is None:
                    continue
                found[key] = AdditionAmountItem(
                    label=label,
                    amount=_stringify_cell(value),
                    source_row=r_idx,
                    source_column=value_col,
                )
    return found


def _amount_item_requires_numeric(key: str) -> bool:
    return key != "sample_method"


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
        # 说明性长文本不是金额/数量/方法摘录的首选值。
        text = str(value).strip()
        if len(text) > 120:
            continue
        if require_short_text and (
            "\n" in text
            or any(term in _norm(text) for term in ("基础操作指引", "进阶实操提示", "易错点", "抽样策略记录"))
        ):
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
            "useful_life_months": ("使用寿命(月)", "使用寿命", "预计使用期间数"),
            "salvage_rate": ("残值率", "预计净残值率", "净残值率"),
            "original_value": (
                "原值",
                "资产原价",
                "固定资产原值",
                "凭证本币总金额",
                "借方(本币)",
                "借方本币",
                "借方金额",
            ),
            "addition_method": ("新增方式", "增加方式", "取得方式"),
        },
        required=("sample_source_no", "sampling_id", "sample_type", "original_value"),
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
                useful_life_months=_value_at(row, mapping.get("useful_life_months")),
                salvage_rate=_value_at(row, mapping.get("salvage_rate")),
            )
        )
    return out


def _extract_tested_samples(rows: list[tuple[Any, ...]]) -> list[AdditionTestedSampleRow]:
    header_row, mapping = _find_table_header(
        rows,
        {
            "sample_type": ("样本类型",),
            "asset_category": ("固定资产类别", "资产类别"),
            "gl_account_code": ("总账账户代码", "总账科目", "GL账户", "GL account"),
            "asset_id": ("固定资产编号", "资产编号", "卡片编号"),
            "asset_name": ("固定资产名称", "资产名称"),
            "original_value": ("资产原价", "原值", "固定资产原值"),
            "capitalized_date": ("资本化日期", "入账开始日期"),
            "useful_life_months": ("使用寿命(月)", "使用寿命", "预计使用期间数"),
            "salvage_rate": ("残值率", "预计净残值率", "净残值率"),
            "depreciation_method": ("折旧方法", "折旧政策", "折旧方式"),
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
                gl_account_code=_value_at(row, mapping.get("gl_account_code")),
                capitalized_date=_value_at(row, mapping.get("capitalized_date")),
                useful_life_months=_value_at(row, mapping.get("useful_life_months")),
                salvage_rate=_value_at(row, mapping.get("salvage_rate")),
                depreciation_method=_value_at(row, mapping.get("depreciation_method")),
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
        if key
        in {
            "asset_id",
            "asset_name",
            "original_value",
            "sample_source_no",
            "sampling_id",
            "sample_type",
        }
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
