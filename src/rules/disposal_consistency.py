from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalSampleOutputDataset,
    DisposalSampleRow,
    DisposalTestSheetDataset,
    DisposalTestedSampleRow,
)
from rules.models import QcIssue, Severity

RULE_ID = "disposal_sample_match"
_MATCH_TOLERANCE = Decimal("0.01")


@dataclass
class DisposalConsistencyPreview:
    execution_path: str | None
    selected_count: int
    tested_count: int
    matched_count: int
    unmatched_selected: list[dict[str, Any]] = field(default_factory=list)
    unmatched_tested: list[dict[str, Any]] = field(default_factory=list)
    sample_type_mismatches: list[dict[str, Any]] = field(default_factory=list)
    amount_mismatches: list[dict[str, Any]] = field(default_factory=list)
    key_item_selected_count: int | None = None
    key_item_tested_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_path": self.execution_path,
            "selected_count": self.selected_count,
            "tested_count": self.tested_count,
            "matched_count": self.matched_count,
            "unmatched_selected": self.unmatched_selected,
            "unmatched_tested": self.unmatched_tested,
            "sample_type_mismatches": self.sample_type_mismatches,
            "amount_mismatches": self.amount_mismatches,
            "key_item_selected_count": self.key_item_selected_count,
            "key_item_tested_count": self.key_item_tested_count,
        }


def build_disposal_consistency_preview(
    disposal_test: DisposalTestSheetDataset | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
    execution_path: DisposalExecutionPathDataset | None = None,
) -> DisposalConsistencyPreview:
    selected = list(disposal_sample_output.selected_samples) if disposal_sample_output else []
    tested = list(disposal_test.tested_samples) if disposal_test else []
    matched_count = 0
    unmatched_selected: list[dict[str, Any]] = []
    unmatched_tested: list[dict[str, Any]] = []
    sample_type_mismatches: list[dict[str, Any]] = []
    amount_mismatches: list[dict[str, Any]] = []
    used_tested: set[int] = set()

    tested_index: dict[str, list[int]] = {}
    for idx, row in enumerate(tested):
        key = _asset_key(row.asset_id)
        if key:
            tested_index.setdefault(key, []).append(idx)

    for sample in selected:
        if _is_replacement_sample(sample.sample_type):
            continue
        key = _asset_key(sample.asset_id)
        match_idx = _first_unused_match(tested_index.get(key, []), used_tested)
        if match_idx is None:
            unmatched_selected.append(_sample_summary(sample))
            continue
        used_tested.add(match_idx)
        matched_count += 1
        tested_row = tested[match_idx]

        if _sample_type_bucket(sample.sample_type) != _sample_type_bucket(tested_row.sample_type):
            sample_type_mismatches.append(
                {
                    "asset_id": sample.asset_id or tested_row.asset_id,
                    "selected_sample_type": sample.sample_type,
                    "tested_sample_type": tested_row.sample_type,
                    "selected_source_row": sample.source_row,
                    "tested_source_row": tested_row.source_row,
                }
            )

        selected_net = _parse_amount(sample.net_value)
        tested_net = _parse_amount(tested_row.net_value)
        if (
            selected_net is not None
            and tested_net is not None
            and abs(selected_net - tested_net) > _MATCH_TOLERANCE
        ):
            amount_mismatches.append(
                {
                    "asset_id": sample.asset_id or tested_row.asset_id,
                    "selected_net_value": sample.net_value,
                    "tested_net_value": tested_row.net_value,
                    "selected_source_row": sample.source_row,
                    "tested_source_row": tested_row.source_row,
                }
            )

    for idx, row in enumerate(tested):
        if idx not in used_tested:
            unmatched_tested.append(_tested_sample_summary(row))

    key_item_selected_count = _key_item_count(disposal_sample_output)
    return DisposalConsistencyPreview(
        execution_path=execution_path.path_kind if execution_path else None,
        selected_count=len([s for s in selected if not _is_replacement_sample(s.sample_type)]),
        tested_count=len(tested),
        matched_count=matched_count,
        unmatched_selected=unmatched_selected,
        unmatched_tested=unmatched_tested,
        sample_type_mismatches=sample_type_mismatches,
        amount_mismatches=amount_mismatches,
        key_item_selected_count=key_item_selected_count,
        key_item_tested_count=len([row for row in tested if _sample_type_bucket(row.sample_type) == "key_item"]),
    )


def check_disposal_sample_match(
    disposal_test: DisposalTestSheetDataset | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
    execution_path: DisposalExecutionPathDataset | None = None,
) -> list[QcIssue]:
    preview = build_disposal_consistency_preview(
        disposal_test,
        disposal_sample_output,
        execution_path=execution_path,
    )
    if preview.execution_path in {"summary_waived", "test_sheet_waiver_note"}:
        return []
    if not preview.selected_count and not preview.tested_count:
        return []

    issues: list[QcIssue] = []
    if preview.selected_count and preview.matched_count < preview.selected_count:
        source_sheet, source_row = _disposal_issue_anchor(
            preferred_sheet=disposal_sample_output.source_sheet if disposal_sample_output else None,
            preferred_row=_first_source_row(preview.unmatched_selected),
            fallback_sheet=disposal_test.source_sheet if disposal_test else None,
            fallback_row=_first_source_row(preview.unmatched_tested),
        )
        issues.append(
            _issue(
                field="sample_match",
                severity=Severity.FAIL,
                message=(
                    "K.02.2a 已选处置样本未全部进入 K.02.2 实际测试："
                    f"已选 {preview.selected_count} 条，匹配到 {preview.matched_count} 条。"
                ),
                suggestion="请核对 K.02.2a 选样输出与 K.02.2 实测样本是否一致；替换样本如未启用，可在底稿中说明。",
                source_sheet=source_sheet or _source_sheet(disposal_sample_output, disposal_test),
                source_row=source_row,
            )
        )

    for item in preview.sample_type_mismatches:
        issues.append(
            _issue(
                field="sample_type",
                severity=Severity.NEED_REVIEW,
                message=(
                    "K.02.2a 与 K.02.2 对同一处置样本的样本类型不一致："
                    f"资产 {item.get('asset_id')}，选样输出为 {item.get('selected_sample_type')}，"
                    f"实测页为 {item.get('tested_sample_type')}。"
                ),
                suggestion="请确认该样本究竟为关键项、代表性样本或替换样本，并使 K.02.2a 与 K.02.2 填写一致。",
                source_sheet=disposal_test.source_sheet if disposal_test else "K.02.2",
                source_row=item.get("tested_source_row"),
            )
        )

    for item in preview.amount_mismatches:
        issues.append(
            _issue(
                field="net_value",
                severity=Severity.WARN,
                message=(
                    "K.02.2a 与 K.02.2 对同一处置样本的净值不一致："
                    f"资产 {item.get('asset_id')}，选样输出净值 {item.get('selected_net_value')}，"
                    f"实测页净值 {item.get('tested_net_value')}。"
                ),
                suggestion="请核对选样输出、处置清单和 K.02.2 实测页的净值口径是否一致。",
                source_sheet=disposal_test.source_sheet if disposal_test else "K.02.2",
                source_row=item.get("tested_source_row"),
            )
        )

    if (
        preview.key_item_selected_count is not None
        and preview.key_item_selected_count != preview.key_item_tested_count
    ):
        source_row = _key_item_count_source_row(disposal_sample_output)
        issues.append(
            _issue(
                field="key_item_count",
                severity=Severity.NEED_REVIEW,
                message=(
                    "K.02.2a 关键项数量与 K.02.2 实测页关键项样本数量不一致："
                    f"K.02.2a={preview.key_item_selected_count}，"
                    f"K.02.2={preview.key_item_tested_count}。"
                ),
                suggestion="请核对关键项识别和代表性样本分类是否在选样输出与实测页保持一致。",
                source_sheet=disposal_sample_output.source_sheet if disposal_sample_output else "K.02.2a",
                source_row=source_row,
            )
        )

    return issues


def _first_unused_match(indices: list[int] | None, used: set[int]) -> int | None:
    for idx in indices or []:
        if idx not in used:
            return idx
    return None


def _key_item_count(disposal_sample_output: DisposalSampleOutputDataset | None) -> int | None:
    if disposal_sample_output is None:
        return None
    item = disposal_sample_output.amounts.get("key_item_count")
    amount = _parse_amount(item.amount if item else None)
    return int(amount) if amount is not None else None


def _key_item_count_source_row(disposal_sample_output: DisposalSampleOutputDataset | None) -> int | None:
    if disposal_sample_output is None:
        return None
    item = disposal_sample_output.amounts.get("key_item_count")
    return item.source_row if item is not None else None


def _first_source_row(items: list[dict[str, Any]]) -> int | None:
    for item in items:
        row = item.get("source_row")
        if isinstance(row, int) and row > 0:
            return row
    return None


def _disposal_issue_anchor(
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
    if preferred_sheet:
        return preferred_sheet, None
    if fallback_sheet:
        return fallback_sheet, None
    return None, None


def _sample_summary(row: DisposalSampleRow) -> dict[str, Any]:
    return {
        "source_row": row.source_row,
        "sample_type": row.sample_type,
        "asset_id": row.asset_id,
        "asset_name": row.asset_name,
        "net_value": row.net_value,
        "sample_source_no": row.sample_source_no,
        "sampling_id": row.sampling_id,
    }


def _tested_sample_summary(row: DisposalTestedSampleRow) -> dict[str, Any]:
    return {
        "source_row": row.source_row,
        "sample_type": row.sample_type,
        "asset_id": row.asset_id,
        "asset_name": row.asset_name,
        "net_value": row.net_value,
    }


def _source_sheet(
    disposal_sample_output: DisposalSampleOutputDataset | None,
    disposal_test: DisposalTestSheetDataset | None,
) -> str:
    if disposal_sample_output is not None:
        return disposal_sample_output.source_sheet
    if disposal_test is not None:
        return disposal_test.source_sheet
    return "K.02.2 / K.02.2a"


def _asset_key(value: Any) -> str:
    return "" if value is None else str(value).strip().lower().replace(" ", "")


def _sample_type_bucket(value: str | None) -> str:
    text = _asset_key(value)
    if "关键项" in text or "keyitem" in text:
        return "key_item"
    if "替换" in text or "replacement" in text:
        return "replacement"
    if "代表性" in text or "representative" in text:
        return "representative"
    return text


def _is_replacement_sample(value: str | None) -> bool:
    return _sample_type_bucket(value) == "replacement"


def _parse_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _issue(
    *,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    source_sheet: str,
    source_row: int | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=RULE_ID,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.02.2",
        source_sheet=source_sheet,
        source_row=source_row,
    )
