from __future__ import annotations

import re
from decimal import Decimal

from ingest.k03_sheet import (
    EXECUTION_PATH_TOD_BY_ITEM,
    K03DetailRow,
    K03SheetDataset,
    load_k03_detail_table,
)
from ingest.lead_sheet import LeadSheetDataset
from ingest.rollforward_sheet import (
    RollforwardSheetDataset,
    get_movement_transaction_amount,
)
from rules.execution_recorder import RuleExecutionRecorder
from rules.k03_observations import (
    K03_LOW_RISK_HOW_RULE_IDS,
    build_k03_not_applicable_observation,
    build_k03_tod_low_risk_observation,
)
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import amount_tolerance, is_blank, parse_amount

RULE_IDS: tuple[str, ...] = (
    "k03_tod_by_item_detail_unreadable",
    "k03_tod_by_item_required_fields",
    "k03_tod_by_item_difference_column",
    "k03_tod_by_item_sad_unavailable",
    "k03_tod_by_item_difference_over_sad",
    "k03_tod_by_item_conclusion_missing",
    "k03_tod_by_item_total_difference_over_sad",
    "k03_tod_by_item_rollforward_depreciation",
)

_AMOUNT_TOL = Decimal("0.01")
_MAX_ROW_FINDINGS = 5
_REQUIRED_FIELDS = (
    "management_depreciation",
    "audit_recalculated_depreciation",
)
_FIELD_LABELS = {
    "management_depreciation": "管理层折旧额",
    "audit_recalculated_depreciation": "审计重新计算折旧额",
    "depreciation_difference": "折旧差异",
    "current_depreciation": "本期折旧额",
}
_EXPLANATION_HEADER_TOKENS = (
    "备注",
    "说明",
    "解释",
    "原因",
    "comment",
    "note",
    "remark",
)
_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "tbd",
    "todo",
    "na",
    "n/a",
    "none",
    "待补",
    "待定",
    "待说明",
    "待解释",
    "不适用",
}


def run_k03_tod_by_item_rules(
    dataset: K03SheetDataset,
    *,
    lead: LeadSheetDataset | None = None,
    rollforward: RollforwardSheetDataset | None = None,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    note = "当前 K.03 工作表不是 by-item 折旧测试执行路径"
    if dataset.execution_path != EXECUTION_PATH_TOD_BY_ITEM:
        for rule_id in RULE_IDS:
            recorder.record_not_applicable(rule_id, note)
            if rule_id in K03_LOW_RISK_HOW_RULE_IDS:
                recorder.record_observation(
                    rule_id,
                    build_k03_not_applicable_observation(rule_id, dataset, reason=note),
                )
        return []

    issues: list[QcIssue] = []
    if dataset.detail_table_ref is None:
        issues = [
            _issue(
                dataset,
                "k03_tod_by_item_detail_unreadable",
                "detail_table",
                Severity.NEED_REVIEW,
                "未能可靠识别 K.03.2 by-item 折旧测试明细表。",
                "请打开 K.03.2 工作表，确认 by-item 折旧测试明细区、表头和合计行是否完整。",
            )
        ]
        _record_k03_execution(
            recorder,
            issues,
            ("k03_tod_by_item_detail_unreadable",),
            dataset=dataset,
            lead=lead,
            rollforward=rollforward,
        )
        return issues

    issues.extend(_check_required_fields(dataset))
    table = load_k03_detail_table(dataset)
    if not table.detail_rows:
        issues.append(
            _issue(
                dataset,
                "k03_tod_by_item_detail_unreadable",
                "detail_table",
                Severity.NEED_REVIEW,
                "已识别 K.03.2 by-item 明细表位置，但未能读取到完整明细行。",
                "请检查工作簿路径、工作表名称和明细表范围是否仍然有效。",
            )
        )
        _record_k03_execution(
            recorder,
            issues,
            ("k03_tod_by_item_required_fields", "k03_tod_by_item_detail_unreadable"),
            dataset=dataset,
            lead=lead,
            rollforward=rollforward,
        )
        return issues

    issues.extend(_check_difference_column(dataset, table.detail_rows + table.total_rows))

    diffs = [_row_diff(row) for row in table.detail_rows]
    material_candidates = [
        (row, diff)
        for row, diff in zip(table.detail_rows, diffs)
        if diff is not None and abs(diff) > _AMOUNT_TOL
    ]
    sad = _sad_from_lead(lead)
    sheet_has_explanation = _has_valid_sheet_explanation(dataset)
    if sad is None:
        if material_candidates:
            issues.append(
                _issue(
                    dataset,
                    "k03_tod_by_item_sad_unavailable",
                    "sad",
                    Severity.NEED_REVIEW,
                    "K.03.2 by-item 折旧测试存在折旧差异，但无法从 K.00 Lead 可靠读取 SAD。",
                    "请先确认 K.00 Lead 中的 SAD，再判断这些差异是否需要进一步说明。",
                    source_row=material_candidates[0][0].source_row,
                )
            )
    else:
        material_rows = [
            (row, diff)
            for row, diff in material_candidates
            if abs(diff) > sad
        ]
        unexplained = [
            (row, diff)
            for row, diff in material_rows
            if not (sheet_has_explanation or _has_valid_row_explanation(row))
        ]
        if len(unexplained) > 1 and not sheet_has_explanation:
            issues.append(
                _issue(
                    dataset,
                    "k03_tod_by_item_conclusion_missing",
                    "conclusion_area",
                    Severity.FAIL,
                    (
                        "K.03.2 by-item 折旧测试存在多项资产层面的超过 SAD 差异，"
                        "但未识别到有效的工作表层面结论或说明。"
                    ),
                    "请在 K.03.2 工作表补充结论或差异说明，覆盖超过 SAD 的折旧差异。",
                    source_row=dataset.conclusion_area.start_row if dataset.conclusion_area else None,
                )
            )
        for row, diff in unexplained[:_MAX_ROW_FINDINGS]:
            issues.append(
                _issue(
                    dataset,
                    "k03_tod_by_item_difference_over_sad",
                    _field_ref(row, "depreciation_difference"),
                    Severity.FAIL,
                    (
                        f"K.03.2 by-item 折旧测试中，资产折旧差异超过 SAD 且未见有效说明："
                        f"资产={_identity(row)}，差异={diff}，SAD={sad}。"
                    ),
                    "请在该行备注/结论或工作表结论区说明超过 SAD 的折旧差异。",
                    source_row=row.source_row,
                    asset_id=_asset_id(row),
                )
            )
        if len(unexplained) > _MAX_ROW_FINDINGS:
            issues.append(
                _issue(
                    dataset,
                    "k03_tod_by_item_difference_over_sad",
                    "depreciation_difference",
                    Severity.FAIL,
                    (
                        f"K.03.2 by-item 折旧测试有 {len(unexplained)} 项资产层面的超过 SAD 差异未说明；"
                        f"当前仅展示前 {_MAX_ROW_FINDINGS} 条明细。"
                    ),
                    "请复核所有超过 SAD 的行，并记录差异说明或后续跟进结论。",
                    source_row=unexplained[_MAX_ROW_FINDINGS][0].source_row,
                )
            )
        issues.extend(_check_total_difference(dataset, table.total_rows, sad, sheet_has_explanation))
        issues.extend(
            _check_rollforward_depreciation(
                dataset,
                table.detail_rows,
                sad,
                sheet_has_explanation,
                rollforward=rollforward,
            )
        )

    _record_k03_execution(
        recorder,
        issues,
        RULE_IDS,
        dataset=dataset,
        lead=lead,
        rollforward=rollforward,
    )
    return issues


def _record_k03_execution(
    recorder: RuleExecutionRecorder,
    issues: list[QcIssue],
    rule_ids: tuple[str, ...],
    *,
    dataset: K03SheetDataset,
    lead: LeadSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> None:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.rule_id] = counts.get(issue.rule_id, 0) + 1
    for rule_id in rule_ids:
        observation = None
        if rule_id in K03_LOW_RISK_HOW_RULE_IDS:
            observation = build_k03_tod_low_risk_observation(
                rule_id,
                dataset,
                issues,
                lead=lead,
                rollforward=rollforward,
            )
        recorder.record_executed(rule_id, counts.get(rule_id, 0), observation=observation)


def _sad_from_lead(lead: LeadSheetDataset | None) -> Decimal | None:
    if lead is None:
        return None
    sad = parse_amount(field_values(lead).get("sad"))
    if sad is None or sad <= 0:
        return None
    return sad


def _check_required_fields(dataset: K03SheetDataset) -> list[QcIssue]:
    mapped = set(dataset.normalized_column_map)
    missing = [field for field in _REQUIRED_FIELDS if field not in mapped]
    if not missing:
        return []
    return [
        _issue(
            dataset,
            "k03_tod_by_item_required_fields",
            ",".join(missing),
            Severity.WARN,
            "K.03.2 by-item 折旧测试缺少关键折旧比对字段："
            + ", ".join(_field_label(field) for field in missing),
            "请确认管理层折旧额和审计重新计算折旧额等栏目是否存在，或是否使用了变体表头。",
            source_row=_detail_table_anchor_row(dataset),
        )
    ]


def _check_difference_column(
    dataset: K03SheetDataset,
    rows: list[K03DetailRow],
) -> list[QcIssue]:
    if "depreciation_difference" not in dataset.normalized_column_map:
        return []
    issues: list[QcIssue] = []
    for row in rows:
        management = parse_amount(row.normalized_values.get("management_depreciation"))
        audit = parse_amount(row.normalized_values.get("audit_recalculated_depreciation"))
        recorded = parse_amount(row.normalized_values.get("depreciation_difference"))
        if management is None or audit is None or recorded is None:
            continue
        expected = management - audit
        tol = amount_tolerance(
            max(abs(expected), abs(recorded), Decimal("1")),
            absolute=_AMOUNT_TOL,
        )
        if abs(recorded - expected) > tol:
            issues.append(
                _issue(
                    dataset,
                    "k03_tod_by_item_difference_column",
                    _field_ref(row, "depreciation_difference"),
                    Severity.FAIL,
                    (
                        "K.03.2 by-item 折旧测试的差异列不等于管理层折旧额"
                        f"减审计重新计算折旧额：资产={_identity(row)}，"
                        f"底稿记录差异={recorded}，应计算差异={expected}。"
                    ),
                    "请检查该行差异公式或粘贴值是否正确。",
                    source_row=row.source_row,
                    asset_id=_asset_id(row),
                )
            )
    return issues[:_MAX_ROW_FINDINGS]


def _check_total_difference(
    dataset: K03SheetDataset,
    total_rows: list[K03DetailRow],
    sad: Decimal,
    sheet_has_explanation: bool,
) -> list[QcIssue]:
    if not total_rows:
        return [
            _issue(
                dataset,
                "k03_tod_by_item_total_difference_over_sad",
                "total_rows",
                Severity.NEED_REVIEW,
                "未识别到 K.03.2 by-item 折旧测试合计行，无法检查总体折旧差异。",
                "请确认 K.03.2 by-item 测试是否包含管理层折旧额和审计重新计算折旧额的合计行。",
            )
        ]
    issues: list[QcIssue] = []
    for row in total_rows:
        diff = _row_diff(row)
        if diff is None:
            continue
        if abs(diff) <= sad:
            continue
        if sheet_has_explanation or _has_valid_row_explanation(row):
            continue
        issues.append(
            _issue(
                dataset,
                "k03_tod_by_item_total_difference_over_sad",
                _field_ref(row, "depreciation_difference"),
                Severity.FAIL,
                f"K.03.2 by-item 折旧测试总体折旧差异超过 SAD 且未见有效说明：差异={diff}，SAD={sad}。",
                "请针对超过 SAD 的总体折旧差异补充总体层面的说明或结论。",
                source_row=row.source_row,
            )
        )
    return issues


def _check_rollforward_depreciation(
    dataset: K03SheetDataset,
    detail_rows: list[K03DetailRow],
    sad: Decimal,
    sheet_has_explanation: bool,
    *,
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    k03_total = _sum_field(detail_rows, "current_depreciation")
    if k03_total is None:
        k03_total = _sum_field(detail_rows, "management_depreciation")
    if k03_total is None:
        return [
            _issue(
                dataset,
                "k03_tod_by_item_rollforward_depreciation",
                "current_depreciation",
                Severity.NEED_REVIEW,
                "无法可靠读取 K.03.2 by-item 折旧测试的本期折旧合计。",
                "请确认 K.03.2 by-item 测试是否包含本期折旧额或管理层折旧额栏目。",
            )
        ]

    rf_amount, rf_row = get_movement_transaction_amount(
        rollforward,
        transaction_key="depreciation",
        measure="accumulated_depreciation",
    )
    if rf_amount is None and rollforward is not None:
        rf_amount = rollforward.table4_rollforward_depreciation
        rf_row = rollforward.table4_rollforward_depreciation_row
    if rf_amount is None:
        return [
            _issue(
                dataset,
                "k03_tod_by_item_rollforward_depreciation",
                "rollforward_depreciation",
                Severity.NEED_REVIEW,
                "无法可靠读取 K.01 后推表中的本期计提折旧金额，不能与 K.03.2 by-item 折旧测试比对。",
                "模板稳定后，请优先使用 K.01 后推表折旧交易行或表4折旧金额作为比对来源。",
            )
        ]

    diff = k03_total - rf_amount
    if abs(diff) <= sad:
        return []
    if sheet_has_explanation:
        return []
    return [
        _issue(
            dataset,
            "k03_tod_by_item_rollforward_depreciation",
            "current_depreciation",
            Severity.FAIL,
            (
                "K.03.2 by-item 折旧测试本期折旧额与 K.01 后推表本期计提折旧金额不一致，"
                f"且差异超过 SAD：K.03={k03_total}，K.01={rf_amount}，差异={diff}，SAD={sad}。"
            ),
            "请说明 K.03 与 K.01 的折旧差异，或更正相关链接/取数金额。",
            source_row=rf_row,
        )
    ]


def _row_diff(row: K03DetailRow) -> Decimal | None:
    recorded = parse_amount(row.normalized_values.get("depreciation_difference"))
    if recorded is not None:
        return recorded
    management = parse_amount(row.normalized_values.get("management_depreciation"))
    audit = parse_amount(row.normalized_values.get("audit_recalculated_depreciation"))
    if management is None or audit is None:
        return None
    return management - audit


def _sum_field(rows: list[K03DetailRow], field: str) -> Decimal | None:
    total = Decimal("0")
    seen = False
    for row in rows:
        amount = parse_amount(row.normalized_values.get(field))
        if amount is None:
            continue
        total += amount
        seen = True
    return total if seen else None


def _has_valid_sheet_explanation(dataset: K03SheetDataset) -> bool:
    texts: list[str] = []
    detail_end = dataset.detail_table_range.end_row if dataset.detail_table_range else None
    for area in (dataset.conclusion_area, dataset.note_area):
        if area and area.text:
            if detail_end and area.start_row and area.start_row <= detail_end:
                continue
            texts.append(area.text)
    return any(_is_valid_explanation(text) for text in texts)


def _detail_table_anchor_row(dataset: K03SheetDataset) -> int | None:
    if dataset.detail_table_ref and dataset.detail_table_ref.header_row:
        return dataset.detail_table_ref.header_row
    if dataset.header_rows:
        return dataset.header_rows[0]
    if dataset.detail_table_range and dataset.detail_table_range.start_row:
        return dataset.detail_table_range.start_row
    return None


def _field_label(field: str) -> str:
    return _FIELD_LABELS.get(field, field)


def _has_valid_row_explanation(row: K03DetailRow) -> bool:
    conclusion = row.normalized_values.get("conclusion")
    if _is_valid_explanation(conclusion):
        return True
    for header, value in row.raw_values.items():
        if _is_explanation_header(header) and _is_valid_explanation(value):
            return True
    return False


def _is_explanation_header(header: str | None) -> bool:
    text = str(header or "").strip().lower()
    return any(token in text for token in _EXPLANATION_HEADER_TOKENS)


def _is_valid_explanation(value: object) -> bool:
    if is_blank(value):
        return False
    text = str(value).strip()
    compact = re.sub(r"[\s。\.，,；;：:（）()\[\]【】]+", "", text).lower()
    if compact in _PLACEHOLDERS:
        return False
    if len(compact) <= 1:
        return False
    return True


def _asset_id(row: K03DetailRow) -> str | None:
    value = row.normalized_values.get("asset_id")
    if is_blank(value):
        return None
    return str(value).strip()


def _identity(row: K03DetailRow) -> str:
    return (
        _asset_id(row)
        or str(row.normalized_values.get("asset_name") or "").strip()
        or f"row {row.source_row}"
    )


def _field_ref(row: K03DetailRow, field: str) -> str:
    cell = row.cell_refs.get(field)
    return f"{field}:{cell}" if cell else field


def _issue(
    dataset: K03SheetDataset,
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    *,
    source_row: int | None = None,
    asset_id: str | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=asset_id,
        rule_id=rule_id,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.03.2",
        source_sheet=dataset.sheet_name,
        source_row=source_row,
    )
