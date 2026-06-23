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
    if dataset.execution_path != EXECUTION_PATH_TOD_BY_ITEM:
        for rule_id in RULE_IDS:
            recorder.record_not_applicable(rule_id, "当前 K.03 工作表不是 by-item 折旧测试执行路径")
        return []

    issues: list[QcIssue] = []
    if dataset.detail_table_ref is None:
        issues = [
            _issue(
                dataset,
                "k03_tod_by_item_detail_unreadable",
                "detail_table",
                Severity.NEED_REVIEW,
                "K.03 TOD-by item detail table was not reliably identified.",
                "Open the K.03.2 sheet and confirm the by-item depreciation test detail area, headers, and total row.",
            )
        ]
        _record_k03_execution(recorder, issues, ("k03_tod_by_item_detail_unreadable",))
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
                "K.03 TOD-by item detail table reference exists, but no full detail rows could be read.",
                "Check whether the workbook path, sheet name, and detail table range are still valid.",
            )
        )
        _record_k03_execution(recorder, issues, ("k03_tod_by_item_required_fields", "k03_tod_by_item_detail_unreadable"))
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
                    "K.03 TOD-by item has depreciation differences, but SAD could not be read reliably from K.00 Lead.",
                    "Confirm the SAD in K.00 Lead before deciding whether the differences require further explanation.",
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
                        "K.03 TOD-by item has multiple asset-level depreciation differences over SAD, "
                        "but no valid sheet-level conclusion or explanation was identified."
                    ),
                    "Add a conclusion or difference explanation on the K.03.2 sheet covering the over-SAD differences.",
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
                        f"K.03 TOD-by item asset depreciation difference exceeds SAD without a valid explanation: "
                        f"asset={_identity(row)}, difference={diff}, SAD={sad}."
                    ),
                    "Explain the over-SAD depreciation difference in the row remark/conclusion or the sheet conclusion area.",
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
                        f"K.03 TOD-by item has {len(unexplained)} unexplained asset-level differences over SAD; "
                        f"showing first {_MAX_ROW_FINDINGS} row findings only."
                    ),
                    "Review all over-SAD rows and document explanations or follow-up conclusions.",
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

    _record_k03_execution(recorder, issues, RULE_IDS)
    return issues


def _record_k03_execution(
    recorder: RuleExecutionRecorder,
    issues: list[QcIssue],
    rule_ids: tuple[str, ...],
) -> None:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.rule_id] = counts.get(issue.rule_id, 0) + 1
    for rule_id in rule_ids:
        recorder.record(rule_id, counts.get(rule_id, 0))


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
            "K.03 TOD-by item is missing key depreciation comparison fields: "
            + ", ".join(missing),
            "Confirm whether management depreciation and audit recalculated depreciation columns are present or mapped under variant headers.",
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
                        "K.03 TOD-by item difference column does not equal management depreciation "
                        f"minus audit recalculated depreciation: asset={_identity(row)}, "
                        f"recorded={recorded}, expected={expected}."
                    ),
                    "Check the difference formula or pasted value for this row.",
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
                "K.03 TOD-by item total row was not identified, so total depreciation difference could not be checked.",
                "Confirm whether the K.03.2 by-item test includes a total row for management and audit recalculated depreciation.",
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
                f"K.03 TOD-by item total depreciation difference exceeds SAD without a valid explanation: difference={diff}, SAD={sad}.",
                "Add a total-level explanation or conclusion for the over-SAD depreciation difference.",
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
                "K.03 TOD-by item current-period depreciation total could not be read reliably.",
                "Confirm whether the K.03.2 by-item test includes current-period depreciation or management depreciation columns.",
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
                "K.01 rollforward depreciation charge could not be read reliably for comparison with K.03 TOD-by item.",
                "Use the K.01 rollforward depreciation transaction row or table 4 depreciation amount when the template is stable.",
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
                "K.03 TOD-by item current-period depreciation does not agree to K.01 rollforward depreciation charge "
                f"and the difference exceeds SAD: K.03={k03_total}, K.01={rf_amount}, difference={diff}, SAD={sad}."
            ),
            "Explain the K.03 vs K.01 depreciation difference or correct the linked depreciation amount.",
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
