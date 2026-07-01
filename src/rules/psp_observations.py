from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from ingest.summary_sheet import SummarySheetDataset
from rules.models import QcIssue, Severity
from rules.psp_completion import normalize_execution_status


def build_psp_completion_observation(
    dataset: SummarySheetDataset,
    issues: Iterable[QcIssue],
    *,
    workbook_sheet_titles: Sequence[str] | None = None,
) -> dict:
    issues = list(issues)
    rows = dataset.programs
    status_counts = Counter(normalize_execution_status(row.execution_status) for row in rows)
    issue_rows = sorted({issue.source_row for issue in issues if issue.source_row is not None})
    selected_rows = _select_rows(rows, issue_rows)
    missing = []
    if not rows:
        missing.append("summary program rows")
    if not dataset.header_row:
        missing.append("summary header row")
    return {
        "checked_data": [
            {
                "sheet": dataset.source_sheet or None,
                "section": "汇总页 PSP / 程序执行清单",
                "location": _rows_location([row.source_row for row in selected_rows]),
                "identified_by": {
                    "sheet_name": dataset.source_sheet or None,
                    "section": "汇总页 PSP / 程序执行清单",
                    "matched_keywords": _matched_keywords(dataset),
                    "matched_rows": _clean_ints(
                        [dataset.header_row] + [row.source_row for row in selected_rows]
                    ),
                    "matched_columns": [
                        binding.column_index for binding in dataset.column_bindings
                    ][:12],
                },
                "key_columns": [
                    "procedure_name",
                    "sheet_ref",
                    "execution_status",
                    "waiver_reason",
                    "notes",
                ],
                "values_read": _row_values(selected_rows),
                "missing_data": missing,
            }
        ],
        "check_logic": (
            "逐行读取汇总页程序清单，检查执行状态是否为空或无法解析；"
            "对标记未执行的程序检查是否填写不执行理由；"
            "对标记已执行的程序检查工作表引用是否能在当前工作簿中找到。"
        ),
        "expected_result": "每个有效程序行应有清晰执行状态；未执行应有可复核理由；已执行应能对应到底稿工作表。",
        "actual_result": (
            f"本次读取 {len(rows)} 行程序记录；"
            f"状态分布：yes={status_counts.get('yes', 0)}，"
            f"no={status_counts.get('no', 0)}，"
            f"empty={status_counts.get('empty', 0)}，"
            f"partial={status_counts.get('partial', 0)}，"
            f"ambiguous={status_counts.get('ambiguous', 0)}；"
            f"工作簿 sheet 数：{len(workbook_sheet_titles or [])}。"
        ),
        "result_summary": _result_summary(issues),
    }


def _select_rows(rows, issue_rows: list[int]):
    if issue_rows:
        selected = [row for row in rows if row.source_row in set(issue_rows)]
        if selected:
            return selected[:5]
    return rows[:5]


def _matched_keywords(dataset: SummarySheetDataset) -> list[str]:
    values = [binding.source_header for binding in dataset.column_bindings if binding.source_header]
    if values:
        return values[:12]
    return ["程序", "工作表", "执行状态", "不执行理由"]


def _row_values(rows) -> list[dict]:
    values: list[dict] = []
    for row in rows:
        values.extend(
            [
                _value_read("程序名称", row.procedure_name, row.source_row, None, "PSP 程序行"),
                _value_read("工作表引用", row.sheet_ref, row.source_row, None, "PSP 程序行"),
                _value_read("执行状态", row.execution_status, row.source_row, None, "PSP 程序行"),
                _value_read("不执行理由", row.waiver_reason, row.source_row, None, "PSP 程序行"),
            ]
        )
    return values[:20]


def _value_read(
    label: str,
    value: object,
    row: int | None,
    column: int | None,
    amount_type: str,
) -> dict:
    return {
        "label": label,
        "value": "" if value is None else str(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": None,
        "amount_type": amount_type,
    }


def _result_summary(issues: list[QcIssue]) -> str:
    finding_count = sum(1 for issue in issues if issue.severity != Severity.PASS)
    if finding_count:
        return f"触发 finding {finding_count} 条。"
    return "未触发 finding。"


def _rows_location(rows: list[int | None]) -> str | None:
    clean = _clean_ints(rows)
    if not clean:
        return None
    return "行 " + ", ".join(str(row) for row in clean[:12])


def _clean_ints(values: list[int | None]) -> list[int]:
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
