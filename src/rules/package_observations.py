from __future__ import annotations

from collections.abc import Iterable, Sequence

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.addition_test_package import _find_package_sheets
from rules.models import QcIssue, Severity


def build_k02_package_complete_observation(
    summary: SummarySheetDataset | None,
    issues: Iterable[QcIssue],
    *,
    workbook_sheet_titles: Sequence[str] | None,
    test_sheet_note: str | None,
    kind: str,
) -> dict:
    issues = list(issues)
    rows = _select_k02_rows(summary.programs if summary else [], kind=kind)
    evidence = _find_package_sheets(workbook_sheet_titles or [], kind=kind)
    missing_data = _missing_data(summary, workbook_sheet_titles, evidence)
    if test_sheet_note:
        note_values = [
            _value_read(
                "test sheet note",
                test_sheet_note,
                None,
                None,
                "limited execution note",
            )
        ]
    else:
        note_values = []

    package_name = "disposal test package" if kind == "disposal" else "addition test package"
    procedure_code = "K.02.2" if kind == "disposal" else "K.02.1"
    return {
        "checked_data": [
            {
                "sheet": summary.source_sheet if summary else None,
                "section": f"{procedure_code} package completeness in summary sheet",
                "location": _rows_location([row.source_row for row in rows]),
                "identified_by": {
                    "sheet_name": summary.source_sheet if summary else None,
                    "section": f"{procedure_code} summary execution rows",
                    "matched_keywords": _row_keywords(rows, kind=kind),
                    "matched_rows": _clean_ints([row.source_row for row in rows]),
                    "matched_columns": _summary_columns(summary),
                },
                "key_columns": [
                    "procedure_name",
                    "sheet_ref",
                    "execution_status",
                    "waiver_reason",
                    "notes",
                ],
                "values_read": _row_values(rows),
                "missing_data": missing_data,
            },
            {
                "sheet": None,
                "section": "workbook sheet titles",
                "location": None,
                "identified_by": {
                    "sheet_name": None,
                    "section": "workbook sheet title scan",
                    "matched_keywords": _package_keywords(kind),
                    "matched_rows": [],
                    "matched_columns": [],
                },
                "key_columns": ["sheet_name"],
                "values_read": _sheet_values(evidence),
                "missing_data": [label for label, title in evidence.items() if not title],
            },
            {
                "sheet": None,
                "section": "test sheet limited execution note",
                "location": None,
                "identified_by": {
                    "sheet_name": None,
                    "section": "runner supplied test sheet note",
                    "matched_keywords": ["limited execution note"],
                    "matched_rows": [],
                    "matched_columns": [],
                },
                "key_columns": ["note"],
                "values_read": note_values,
                "missing_data": [] if test_sheet_note else ["test sheet note"],
            },
        ],
        "check_logic": (
            f"Read the summary execution rows for {procedure_code}, scan workbook sheet titles "
            f"for the expected {package_name} components, and keep any existing limited "
            "execution note as evidence. The observation records the data used by the rule only."
        ),
        "expected_result": (
            f"When {procedure_code} is marked executed, the workbook should include the list, "
            "test working paper, and sampling output sheets, unless a documented limited "
            "execution note explains the scope."
        ),
        "actual_result": _actual_result(evidence, test_sheet_note),
        "result_summary": _result_summary(issues),
    }


def _select_k02_rows(rows: Sequence[PspProgramRow], *, kind: str) -> list[PspProgramRow]:
    selected = [row for row in rows if _is_k02_row(row, kind=kind)]
    return selected[:8]


def _is_k02_row(row: PspProgramRow, *, kind: str) -> bool:
    text = f"{row.procedure_name or ''} {row.sheet_ref or ''}".lower().replace(".", "")
    if kind == "disposal":
        return "k022" in text or "disposal" in text
    return "k021" in text or "addition" in text


def _row_keywords(rows: Sequence[PspProgramRow], *, kind: str) -> list[str]:
    keywords = _package_keywords(kind)
    for row in rows[:5]:
        if row.procedure_name:
            keywords.append(str(row.procedure_name))
        if row.sheet_ref:
            keywords.append(str(row.sheet_ref))
    return keywords[:12]


def _package_keywords(kind: str) -> list[str]:
    if kind == "disposal":
        return ["K.02.2", "disposal", "disposal list", "disposal test", "sampling output"]
    return ["K.02.1", "addition", "addition list", "addition test", "sampling output"]


def _summary_columns(summary: SummarySheetDataset | None) -> list[int]:
    if summary is None:
        return []
    return [binding.column_index for binding in summary.column_bindings][:12]


def _row_values(rows: Sequence[PspProgramRow]) -> list[dict]:
    values: list[dict] = []
    for row in rows:
        values.extend(
            [
                _value_read("procedure name", row.procedure_name, row.source_row, None, "summary row"),
                _value_read("sheet reference", row.sheet_ref, row.source_row, None, "summary row"),
                _value_read("execution status", row.execution_status, row.source_row, None, "summary row"),
                _value_read("waiver reason", row.waiver_reason, row.source_row, None, "summary row"),
                _value_read("notes", row.notes, row.source_row, None, "summary row"),
            ]
        )
    return values[:30]


def _sheet_values(evidence: dict[str, str | None]) -> list[dict]:
    return [
        _value_read(label, title, None, None, "workbook sheet title")
        for label, title in evidence.items()
        if title
    ]


def _missing_data(
    summary: SummarySheetDataset | None,
    workbook_sheet_titles: Sequence[str] | None,
    evidence: dict[str, str | None],
) -> list[str]:
    missing: list[str] = []
    if summary is None:
        missing.append("summary sheet")
    elif not summary.programs:
        missing.append("summary execution rows")
    if not workbook_sheet_titles:
        missing.append("workbook sheet titles")
    missing.extend(label for label, title in evidence.items() if not title)
    return missing


def _actual_result(evidence: dict[str, str | None], test_sheet_note: str | None) -> str:
    found = [f"{label}: {title}" for label, title in evidence.items() if title]
    missing = [label for label, title in evidence.items() if not title]
    found_text = "; ".join(found) if found else "no package component sheet matched"
    missing_text = ", ".join(missing) if missing else "none"
    note_text = "present" if test_sheet_note else "not recorded"
    return (
        f"Matched package components: {found_text}. "
        f"Missing package components: {missing_text}. "
        f"Limited execution note: {note_text}."
    )


def _result_summary(issues: list[QcIssue]) -> str:
    finding_count = sum(1 for issue in issues if issue.severity != Severity.PASS)
    if finding_count:
        return f"Triggered {finding_count} finding(s)."
    return "No finding triggered."


def _value_read(
    label: str,
    value: object,
    row: int | None,
    column: int | None,
    amount_type: str,
) -> dict:
    return {
        "label": label,
        "value": "" if value is None else _short_text(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": None,
        "amount_type": amount_type,
    }


def _rows_location(rows: list[int | None]) -> str | None:
    clean = _clean_ints(rows)
    if not clean:
        return None
    return "rows " + ", ".join(str(row) for row in clean[:12])


def _clean_ints(values: Sequence[int | None]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result[:12]


def _cell(row: int | None, column: int | None) -> str | None:
    if row is None or column is None:
        return None
    return f"{_column_letter(column)}{row}"


def _column_letter(column: int) -> str:
    letters = ""
    while column > 0:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _short_text(value: object, limit: int = 300) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
