from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionSampleOutputDataset,
    AdditionSampleRow,
    AdditionTestSheetDataset,
    AdditionTestedSampleRow,
)
from rules.models import QcIssue, Severity

_MATCH_TOLERANCE = Decimal("0.01")


@dataclass
class AdditionConsistencyPreview:
    execution_path: str | None
    selected_count: int
    tested_count: int
    matched_count: int
    unmatched_selected: list[dict[str, Any]] = field(default_factory=list)
    unmatched_tested: list[dict[str, Any]] = field(default_factory=list)
    key_item_selected_count: int = 0
    key_item_tested_count: int = 0
    key_item_selected_amount: str | None = None
    key_item_tested_amount: str | None = None
    sample_method: str | None = None
    exception_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_path": self.execution_path,
            "selected_count": self.selected_count,
            "tested_count": self.tested_count,
            "matched_count": self.matched_count,
            "unmatched_selected": self.unmatched_selected,
            "unmatched_tested": self.unmatched_tested,
            "key_item_selected_count": self.key_item_selected_count,
            "key_item_tested_count": self.key_item_tested_count,
            "key_item_selected_amount": self.key_item_selected_amount,
            "key_item_tested_amount": self.key_item_tested_amount,
            "sample_method": self.sample_method,
            "exception_flags": self.exception_flags,
            "notes": self.notes,
        }


def build_addition_consistency_preview(
    addition_test: AdditionTestSheetDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
    execution_path: AdditionExecutionPathDataset | None = None,
) -> AdditionConsistencyPreview:
    selected_all = list(addition_sample_output.selected_samples) if addition_sample_output else []
    selected = [row for row in selected_all if not _is_replacement_sample(row.sample_type)]
    tested = list(addition_test.tested_samples) if addition_test else []
    matched_count = 0
    unmatched_selected: list[dict[str, Any]] = []
    unmatched_tested: list[dict[str, Any]] = []
    used_tested: set[int] = set()
    tested_index = {}
    for idx, row in enumerate(tested):
        for key in _sample_keys(row.asset_id, row.asset_name, row.original_value):
            tested_index.setdefault(key, []).append(idx)

    for sample in selected:
        match_idx = _match_selected_sample(sample, tested, tested_index, used_tested)
        if match_idx is None:
            unmatched_selected.append(_sample_summary(sample))
            continue
        used_tested.add(match_idx)
        matched_count += 1

    for idx, row in enumerate(tested):
        if idx not in used_tested:
            unmatched_tested.append(_tested_sample_summary(row))

    key_item_selected = [row for row in selected if _is_key_item_sample(row.sample_type)]
    key_item_tested = [row for row in tested if _is_key_item_sample(row.sample_type)]
    sample_method = None
    if addition_sample_output:
        sample_item = addition_sample_output.amounts.get("sample_method")
        if sample_item and sample_item.amount is not None:
            sample_method = str(sample_item.amount)

    preview = AdditionConsistencyPreview(
        execution_path=execution_path.path_kind if execution_path else None,
        selected_count=len(selected),
        tested_count=len(tested),
        matched_count=matched_count,
        unmatched_selected=unmatched_selected,
        unmatched_tested=unmatched_tested,
        key_item_selected_count=len(key_item_selected),
        key_item_tested_count=len(key_item_tested),
        key_item_selected_amount=_sum_amount(row.original_value for row in key_item_selected),
        key_item_tested_amount=_sum_amount(row.original_value for row in key_item_tested),
        sample_method=sample_method,
        exception_flags=_exception_flags(addition_test, tested),
        notes=list(addition_test.notes if addition_test else []),
    )
    return preview


def check_addition_sample_match(
    addition_test: AdditionTestSheetDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
    execution_path: AdditionExecutionPathDataset | None = None,
) -> list[QcIssue]:
    preview = build_addition_consistency_preview(
        addition_test,
        addition_sample_output,
        execution_path=execution_path,
    )
    if not preview.selected_count and not preview.tested_count:
        return []
    if preview.execution_path in {"summary_waived", "test_sheet_waiver_note"}:
        return []

    issues: list[QcIssue] = []
    # Exception-summary recognition is diagnostic only for K.02.1; it should
    # not create a finding unless another rule identifies a concrete mismatch.
    preview.exception_flags = []
    sample_output_sheet = addition_sample_output.source_sheet if addition_sample_output else None
    test_sheet = addition_test.source_sheet if addition_test else None

    if preview.selected_count and preview.matched_count < preview.selected_count:
        source_sheet, source_row = _addition_issue_anchor(
            preferred_sheet=sample_output_sheet,
            preferred_row=_first_source_row(preview.unmatched_selected),
            fallback_sheet=test_sheet,
            fallback_row=_first_source_row(preview.unmatched_tested),
        )
        issues.append(
            _issue(
                field="sample_match",
                severity=Severity.FAIL,
                message=(
                    f"K.02.1a 已选样本与 K.02.1 测试样本不一致："
                    f"已选 {preview.selected_count} 条，匹配到 {preview.matched_count} 条。"
                ),
                suggestion=(
                    "请核对 K.02.1a 已选取样本是否全部进入 K.02.1 实际测试，"
                    "并确认是否存在漏测或样本替换未记录。"
                ),
                source_sheet=source_sheet,
                source_row=source_row,
            )
        )

    sel_amt = _parse_amount(preview.key_item_selected_amount)
    test_amt = _parse_amount(preview.key_item_tested_amount)
    if sel_amt is not None and test_amt is not None and abs(sel_amt - test_amt) > _MATCH_TOLERANCE:
        source_sheet, source_row = _key_item_anchor(addition_test, addition_sample_output)
        issues.append(
            _issue(
                field="key_item_amount",
                severity=Severity.WARN,
                message=(
                    "K.02.1a 关键项金额与 K.02.1 关键项测试样本原值合计不一致："
                    f"选样输出 {preview.key_item_selected_amount}，测试样本 {preview.key_item_tested_amount}。"
                ),
                suggestion=(
                    "请核对关键项金额来源、关键项样本是否完整，"
                    "以及定量关键项是否与实际测试样本一致。"
                ),
                source_sheet=source_sheet,
                source_row=source_row,
            )
        )

    if preview.exception_flags and not _has_exception_note(addition_test):
        issues.append(
            _issue(
                field="exception_summary",
                severity=Severity.NEED_REVIEW,
                message=(
                    "新增测试样本存在差异或属性 N，但未识别到明确异常说明。"
                ),
                suggestion=(
                    "请在 K.02.1 的异常情况区补充异常分析，"
                    "说明差异原因或属性 N 的处理结果。"
                ),
                source_sheet=test_sheet,
                source_row=_first_exception_source_row(addition_test),
            )
        )

    for item in preview.unmatched_selected:
        issues.append(
            _issue(
                field="sample_match",
                severity=Severity.FAIL,
                message=(
                    "K.02.1a 已选样本未能在 K.02.1 中找到对应测试样本："
                    f"{item.get('sample_type') or '样本'} / "
                    f"{item.get('asset_id') or item.get('asset_name') or '未知'}。"
                ),
                suggestion="请补充对应测试样本或修正选样输出与测试底稿的一致性。",
                source_sheet=sample_output_sheet,
                source_row=item.get("source_row"),
            )
        )

    for item in preview.unmatched_tested:
        if _is_replacement_sample(item.get("sample_type")):
            continue
        issues.append(
            _issue(
                field="sample_match",
                severity=Severity.NEED_REVIEW,
                message=(
                    "K.02.1 中存在未在 K.02.1a 选样输出中识别到的测试样本："
                    f"{item.get('sample_type') or '样本'} / "
                    f"{item.get('asset_id') or item.get('asset_name') or '未知'}。"
                ),
                suggestion="请确认该样本是否为替换样本、关键项扩展样本或手工补充样本。",
                source_sheet=test_sheet,
                source_row=item.get("source_row"),
            )
        )

    return issues


def _match_selected_sample(
    sample: AdditionSampleRow,
    tested: list[AdditionTestedSampleRow],
    tested_index: dict[tuple[str, str, str], list[int]],
    used_tested: set[int],
) -> int | None:
    keys = _sample_keys(sample.asset_id, sample.asset_name, sample.original_value)
    for key in keys:
        for idx in tested_index.get(key, []):
            if idx not in used_tested:
                return idx
    return None


def _sample_keys(
    asset_id: object,
    asset_name: object,
    amount: object,
) -> list[tuple[str, str, str]]:
    aid = _norm(asset_id)
    name = _norm(asset_name)
    amt = _norm(amount)
    keys = []
    if aid or amt:
        keys.append((aid, "", amt))
    if name or amt:
        keys.append(("", name, amt))
    if aid or name:
        keys.append((aid, name, amt))
    if amt:
        keys.append(("", "", amt))
    return keys


def _sample_summary(row: AdditionSampleRow) -> dict[str, Any]:
    return {
        "source_row": row.source_row,
        "sample_type": row.sample_type,
        "asset_id": row.asset_id,
        "asset_name": row.asset_name,
        "original_value": row.original_value,
        "addition_method": row.addition_method,
        "sample_source_no": row.sample_source_no,
        "sampling_id": row.sampling_id,
    }


def _tested_sample_summary(row: AdditionTestedSampleRow) -> dict[str, Any]:
    return {
        "source_row": row.source_row,
        "sample_type": row.sample_type,
        "asset_id": row.asset_id,
        "asset_name": row.asset_name,
        "original_value": row.original_value,
        "evidence_amount": row.evidence_amount,
        "amount_difference": row.amount_difference,
        "attribute_results": row.attribute_results,
    }


def _sum_amount(values: Any) -> str | None:
    total = Decimal("0")
    seen = False
    for value in values:
        amount = _parse_amount(value)
        if amount is None:
            continue
        total += amount
        seen = True
    if not seen:
        return None
    return _format_amount(total)


def _parse_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    if text in {"-", "—"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _format_amount(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "")


def _is_key_item_sample(sample_type: str | None) -> bool:
    text = _norm(sample_type)
    return "关键项" in text or "keyitem" in text


def _is_replacement_sample(sample_type: str | None) -> bool:
    text = _norm(sample_type)
    return "替换" in text or "replacement" in text


def _has_exception_note(addition_test: AdditionTestSheetDataset | None) -> bool:
    if addition_test is None:
        return False
    if any(
        assessment.module_key == "exception_summary" and assessment.status == "recognized"
        for assessment in addition_test.module_assessments
    ):
        return True
    if addition_test.waiver_note_text:
        return True
    for sample in addition_test.tested_samples:
        text = _norm(sample.evidence_description)
        if "异常" in text or "无异常" in text:
            return True
    return any("无异常" in _norm(note) or "异常" in _norm(note) for note in addition_test.notes)


def _exception_flags(
    addition_test: AdditionTestSheetDataset | None,
    tested_samples: list[AdditionTestedSampleRow],
) -> list[str]:
    flags: list[str] = []
    for sample in tested_samples:
        diff = _parse_amount(sample.amount_difference)
        if diff is not None and diff != 0:
            flags.append(f"差异@{sample.source_row}")
        if any(str(v).strip().upper() == "N" for v in sample.attribute_results if v is not None):
            flags.append(f"属性N@{sample.source_row}")
    if addition_test and addition_test.waiver_note_text:
        flags.append("waiver_note")
    return flags


def _first_source_row(items: list[dict[str, Any]]) -> int | None:
    for item in items:
        row = item.get("source_row")
        if isinstance(row, int) and row > 0:
            return row
    return None


def _addition_issue_anchor(
    *,
    preferred_sheet: str | None,
    preferred_row: int | None,
    fallback_sheet: str | None,
    fallback_row: int | None,
) -> tuple[str | None, int | None]:
    if preferred_sheet and preferred_row:
        return preferred_sheet, preferred_row
    if fallback_sheet and fallback_row:
        return fallback_sheet, fallback_row
    return preferred_sheet or fallback_sheet, preferred_row or fallback_row


def _key_item_anchor(
    addition_test: AdditionTestSheetDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
) -> tuple[str | None, int | None]:
    if addition_sample_output:
        for row in addition_sample_output.selected_samples:
            if _is_key_item_sample(row.sample_type):
                return addition_sample_output.source_sheet, row.source_row
    if addition_test:
        for row in addition_test.tested_samples:
            if _is_key_item_sample(row.sample_type):
                return addition_test.source_sheet, row.source_row
    return (
        addition_sample_output.source_sheet if addition_sample_output else (
            addition_test.source_sheet if addition_test else None
        ),
        None,
    )


def _first_exception_source_row(addition_test: AdditionTestSheetDataset | None) -> int | None:
    if addition_test is None:
        return None
    for sample in addition_test.tested_samples:
        diff = _parse_amount(sample.amount_difference)
        if diff is not None and diff != 0:
            return sample.source_row
        if any(str(v).strip().upper() == "N" for v in sample.attribute_results if v is not None):
            return sample.source_row
    return None


def _issue(
    *,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    source_sheet: str | None = None,
    source_row: int | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id="addition_sample_match",
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.02.1",
        source_sheet=source_sheet or "K.02.1 / K.02.1a",
        source_row=source_row,
    )
