"""将 findings 写回底稿副本：主汇总 sheet + FA list 明细 sheet + 单元格批注。"""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from report.summary import QcReport, worst_severity
from rules.models import QcIssue, Severity

COMMENTS_SHEET_NAME = "Comments【归档前删除】"
FA_LIST_COMMENTS_SHEET_NAME = "Comments【FA list】"
_COMMENT_HEADERS = (
    "EY Ref.",
    "Tab Ref.",
    "Cell Ref.",
    "Question/Comment",
    "Answer/Comment",
    "Closed?",
)

_DEFAULT_COMMENT_COL = 2
_AUTHOR = "FA-QC"
_FILL_FAIL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
_FILL_WARN = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
_FILL_NR = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
_HEADER_FONT = Font(bold=True)

_SEV_RANK = {Severity.FAIL: 0, Severity.WARN: 1, Severity.NEED_REVIEW: 2}


def annotated_workbook_path(input_path: str | Path) -> Path:
    p = Path(input_path)
    return p.with_name(f"{p.stem}_qc_annotated.xlsx")


def _cell_ref_a1(row: int | None, col: int = _DEFAULT_COMMENT_COL) -> str:
    if not row or row < 1:
        return ""
    return f"${get_column_letter(col)}${row}"


def _issue_comment_text(issue: QcIssue) -> str:
    code = issue.dict_rule_code or issue.rule_id
    lines = [f"[{issue.severity.value}] {code}"]
    if issue.field:
        lines.append(f"字段: {issue.field}")
    lines.append(issue.message)
    if issue.suggestion:
        lines.append(f"建议: {issue.suggestion}")
    return "\n".join(lines)


def _question_text(issue: QcIssue) -> str:
    code = issue.dict_rule_code or issue.rule_id
    return f"[{issue.severity.value}] {code}: {issue.message}"


def _finding_issues(report: QcReport) -> list[QcIssue]:
    return [i for i in report.issues if i.severity != Severity.PASS]


def split_fa_list_issues(issues: list[QcIssue]) -> tuple[list[QcIssue], list[QcIssue]]:
    fa_list: list[QcIssue] = []
    other: list[QcIssue] = []
    for issue in issues:
        if issue.procedure_code == "FA_LIST":
            fa_list.append(issue)
        else:
            other.append(issue)
    return fa_list, other


def _aggregate_fa_list_issues(
    issues: list[QcIssue],
) -> list[tuple[QcIssue, int, list[str]]]:
    """按 (rule_id, field, severity) 合并 FA list 共性问题。"""
    buckets: dict[tuple[str, str, Severity], list[QcIssue]] = defaultdict(list)
    for issue in issues:
        key = (issue.rule_id, issue.field or "", issue.severity)
        buckets[key].append(issue)
    merged: list[tuple[QcIssue, int, list[str]]] = []
    for group in buckets.values():
        rep = group[0]
        sheets = sorted({i.source_sheet for i in group if i.source_sheet})
        merged.append((rep, len(group), sheets))
    merged.sort(
        key=lambda x: (
            _SEV_RANK.get(x[0].severity, 9),
            x[0].rule_id,
            x[0].field or "",
        )
    )
    return merged


def _fa_list_summary_question(rep: QcIssue, count: int) -> str:
    code = rep.dict_rule_code or rep.rule_id
    field_part = f"（字段 {rep.field}）" if rep.field else ""
    return (
        f"[{rep.severity.value}] {code}{field_part} — 共 {count} 条同类 finding；"
        f"明细见 sheet「{FA_LIST_COMMENTS_SHEET_NAME}」。"
        f" 代表说明: {rep.message}"
    )


def build_main_comments_rows(
    other_issues: list[QcIssue],
    fa_list_issues: list[QcIssue],
) -> list[tuple]:
    """主汇总表：其他程序逐条 + FA list 仅共性合并行。"""
    rows: list[tuple] = []
    ey = 0

    for issue in sorted(
        other_issues,
        key=lambda i: (_SEV_RANK.get(i.severity, 9), i.source_sheet or "", i.source_row or 0),
    ):
        ey += 1
        rows.append(
            (
                ey,
                issue.source_sheet or "—",
                _cell_ref_a1(issue.source_row),
                _question_text(issue),
                issue.suggestion or None,
                "No",
            )
        )

    for rep, count, sheets in _aggregate_fa_list_issues(fa_list_issues):
        ey += 1
        if not sheets:
            tab = "FA list"
        elif len(sheets) == 1:
            tab = sheets[0]
        else:
            tab = f"{sheets[0]} 等（{len(sheets)} 张表）"
        rows.append(
            (
                ey,
                tab or "FA list",
                f"见附表 {FA_LIST_COMMENTS_SHEET_NAME}",
                _fa_list_summary_question(rep, count),
                rep.suggestion or None,
                "No",
            )
        )

    return rows


def build_fa_list_detail_rows(fa_list_issues: list[QcIssue]) -> list[tuple]:
    sorted_issues = sorted(
        fa_list_issues,
        key=lambda i: (_SEV_RANK.get(i.severity, 9), i.source_sheet or "", i.source_row or 0),
    )
    rows: list[tuple] = []
    for idx, issue in enumerate(sorted_issues, start=1):
        rows.append(
            (
                idx,
                issue.source_sheet or "—",
                _cell_ref_a1(issue.source_row),
                _question_text(issue),
                issue.suggestion or None,
                "No",
            )
        )
    return rows


def build_comments_rows(issues: list[QcIssue]) -> list[tuple]:
    """兼容旧接口：等同主表行（含 FA 合并逻辑）。"""
    fa, other = split_fa_list_issues(issues)
    return build_main_comments_rows(other, fa)


def _write_sheet_rows(
    ws,
    rows: list[tuple],
    *,
    source_file: str,
    footer_extra: str = "",
) -> None:
    ws.delete_rows(1, ws.max_row or 1)
    for col, header in enumerate(_COMMENT_HEADERS, start=1):
        c = ws.cell(row=1, column=col, value=header)
        c.font = _HEADER_FONT
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, val in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=val)
    if not rows:
        ws.cell(row=2, column=1, value="（本区无 findings）")
    summary_row = len(rows) + 3
    ws.cell(row=summary_row, column=1, value=f"源文件: {Path(source_file).name}{footer_extra}")


def _place_sheet_at_index(wb: openpyxl.Workbook, name: str, index: int):
    if name in wb.sheetnames:
        ws = wb[name]
        wb.remove(ws)
    else:
        ws = wb.create_sheet(name)
    wb._sheets.insert(index, ws)
    return ws


def _fill_for_severity(sev: Severity) -> PatternFill | None:
    if sev == Severity.FAIL:
        return _FILL_FAIL
    if sev == Severity.WARN:
        return _FILL_WARN
    if sev == Severity.NEED_REVIEW:
        return _FILL_NR
    return None


def _apply_cell_annotations(wb: openpyxl.Workbook, issues: list[QcIssue]) -> int:
    count = 0
    by_sheet: dict[str, list[QcIssue]] = {}
    for issue in issues:
        sheet = (issue.source_sheet or "").strip()
        if not sheet or sheet not in wb.sheetnames:
            continue
        by_sheet.setdefault(sheet, []).append(issue)

    for sheet_name, sheet_issues in by_sheet.items():
        ws = wb[sheet_name]
        for issue in sheet_issues:
            row = issue.source_row
            if not row or row < 1:
                continue
            cell = ws.cell(row=row, column=_DEFAULT_COMMENT_COL)
            cell.comment = Comment(_issue_comment_text(issue), _AUTHOR)
            fill = _fill_for_severity(issue.severity)
            if fill:
                cell.fill = fill
            count += 1
    return count


def export_annotated_workbook(
    report: QcReport,
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """
    生成带标注底稿副本：

    - Sheet1 ``Comments【归档前删除】``：其他程序 findings 逐条 + FA list 共性问题合并行
    - Sheet2 ``Comments【FA list】``：FA list findings 逐条明细
    - 业务 sheet：单元格批注（有 source_row 时）
    """
    input_path = Path(input_path)
    if input_path.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ValueError("仅支持 Excel 底稿（.xlsx / .xlsm）生成标注副本")

    out = Path(output_path) if output_path else annotated_workbook_path(input_path)
    shutil.copy2(input_path, out)

    issues = _finding_issues(report)
    fa_issues, other_issues = split_fa_list_issues(issues)
    overall = worst_severity([i.severity for i in issues]) if issues else Severity.PASS
    footer = (
        f" | 整体 {overall.value}"
        f" | 主表: 其他 {len(other_issues)} 条 + FA 共性 {len(_aggregate_fa_list_issues(fa_issues))} 行"
        f" | FA 明细 {len(fa_issues)} 条"
    )

    wb = openpyxl.load_workbook(out)
    main_ws = _place_sheet_at_index(wb, COMMENTS_SHEET_NAME, 0)
    _write_sheet_rows(
        main_ws,
        build_main_comments_rows(other_issues, fa_issues),
        source_file=str(input_path),
        footer_extra=footer,
    )
    fa_ws = _place_sheet_at_index(wb, FA_LIST_COMMENTS_SHEET_NAME, 1)
    _write_sheet_rows(
        fa_ws,
        build_fa_list_detail_rows(fa_issues),
        source_file=str(input_path),
        footer_extra=" | FA list 专项明细",
    )
    _apply_cell_annotations(wb, issues)
    wb.save(out)
    wb.close()
    return out


def comments_summary_stats(report: QcReport) -> dict[str, int | str]:
    issues = _finding_issues(report)
    fa_issues, other_issues = split_fa_list_issues(issues)
    overall = worst_severity([i.severity for i in issues]) if issues else Severity.PASS
    return {
        "overall_severity": overall.value,
        "finding_count": len(issues),
        "fail_count": sum(1 for i in issues if i.severity == Severity.FAIL),
        "warn_count": sum(1 for i in issues if i.severity == Severity.WARN),
        "need_review_count": sum(1 for i in issues if i.severity == Severity.NEED_REVIEW),
        "comments_sheet": COMMENTS_SHEET_NAME,
        "fa_list_comments_sheet": FA_LIST_COMMENTS_SHEET_NAME,
        "other_finding_count": len(other_issues),
        "fa_list_finding_count": len(fa_issues),
        "fa_list_summary_row_count": len(_aggregate_fa_list_issues(fa_issues)),
    }
