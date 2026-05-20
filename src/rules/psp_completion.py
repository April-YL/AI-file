from __future__ import annotations

import re
from collections.abc import Sequence

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.models import QcIssue, Severity
from rules.psp_sheet_matcher import count_non_empty_cells, find_matching_sheet

RULE_ID = "psp_completion"

_MIN_WAIVER_LEN = 8
_MIN_SHEET_MATCH_SCORE = 0.48
_STRONG_SHEET_MATCH_SCORE = 0.72
_MIN_SUBSTANCE_CELLS = 8

_K_SEGMENT = re.compile(r"[kK]\.\d+(?:\.\d+)*[a-zA-Z]?")

_SKIP_PROCEDURE_NAMES = frozenset(
    {
        "程序",
        "程序名称",
        "审计程序",
        "返回汇总页",
        "返回汇总",
    }
)

_EXEC_YES = re.compile(
    r"^(是|已执行|执行|完成|y|yes|true|√|✓|1|done)$",
    re.IGNORECASE,
)
_EXEC_NO = re.compile(
    r"^(否|不执行|未执行|拒绝|n|no|false|0|不适用|n/a|na)$",
    re.IGNORECASE,
)
_EXEC_PARTIAL = re.compile(r"部分|partial", re.IGNORECASE)


def _should_skip_row(row: PspProgramRow) -> bool:
    name = (row.procedure_name or "").strip()
    if not name or name in _SKIP_PROCEDURE_NAMES:
        return True
    if name.startswith("返回"):
        return True
    return False


def _normalize_status(raw: str | None) -> str:
    if raw is None:
        return "empty"
    text = str(raw).strip()
    if not text:
        return "empty"
    if _EXEC_PARTIAL.search(text):
        return "partial"
    if _EXEC_YES.search(text):
        return "yes"
    if _EXEC_NO.search(text):
        return "no"
    if "不执行" in text or "未执行" in text:
        return "no"
    if "部分" in text:
        return "partial"
    if "执行" in text and "不" not in text:
        return "yes"
    return "ambiguous"


def _fallback_sheet_ref_from_procedure(name: str | None) -> str | None:
    if not name:
        return None
    m = _K_SEGMENT.search(name)
    return m.group(0) if m else None


def _ref_for_sheet_match(row: PspProgramRow) -> str | None:
    ref = (row.sheet_ref or "").strip()
    if ref:
        return ref
    return _fallback_sheet_ref_from_procedure(row.procedure_name)


def _check_yes_program_sheet(
    row: PspProgramRow,
    source_sheet: str,
    *,
    workbook_sheet_titles: Sequence[str] | None,
    workbook_path: str | None,
) -> list[QcIssue]:
    """已执行程序与工作表名称及表内非空内容的形式勾稽（可选，需传入 sheet 列表）。"""
    issues: list[QcIssue] = []
    if workbook_sheet_titles is None:
        return issues

    label = row.procedure_name
    if row.sheet_ref:
        label = f"{label} ({row.sheet_ref})"

    ref = _ref_for_sheet_match(row)
    if not ref:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="sheet_ref",
                severity=Severity.NEED_REVIEW,
                message=f"程序「{label}」标为已执行，但程序页/工作表引用为空，无法与底稿工作表勾稽",
                suggestion="补充程序页列或与底稿一致的工作表引用（含 K.xx 程序页编号）",
                procedure_code="SUMMARY",
                source_sheet=source_sheet,
                source_row=row.source_row,
            )
        )
        return issues

    titles_list = list(workbook_sheet_titles)
    if not titles_list:
        return issues

    matched, score, _reason = find_matching_sheet(ref, titles_list)
    if matched is None or score < _MIN_SHEET_MATCH_SCORE:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="sheet_ref",
                severity=Severity.FAIL,
                message=(
                    f"程序「{label}」标为已执行，但工作簿中未找到与程序页引用「{ref}」"
                    "相匹配的工作表（已做名称规范化与模糊匹配）"
                ),
                suggestion="核对程序页名称与底稿工作表名称是否一致，或修正汇总页超链接目标",
                procedure_code="SUMMARY",
                source_sheet=source_sheet,
                source_row=row.source_row,
            )
        )
        return issues

    if score < _STRONG_SHEET_MATCH_SCORE:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="sheet_ref",
                severity=Severity.NEED_REVIEW,
                message=(
                    f"程序「{label}」对应的底稿页可能为「{matched}」"
                    f"（名称匹配置信度约 {score:.0%}），请人工确认是否为正确工作表"
                ),
                suggestion="确认汇总页程序页与打开底稿后的实际表名一致",
                procedure_code="SUMMARY",
                source_sheet=source_sheet,
                source_row=row.source_row,
            )
        )

    if workbook_path and matched:
        ncells = count_non_empty_cells(workbook_path, matched, max_rows=40)
        if 0 <= ncells < _MIN_SUBSTANCE_CELLS:
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field="sheet_substance",
                    severity=Severity.WARN,
                    message=(
                        f"程序「{label}」对应工作表「{matched}」前若干行有效内容较少"
                        f"（非空单元格约 {ncells} 个），请确认是否已实质执行并完成底稿"
                    ),
                    suggestion="检查该工作表是否为空模板或未保存结果",
                    procedure_code="SUMMARY",
                    source_sheet=source_sheet,
                    source_row=row.source_row,
                )
            )

    return issues


def _check_program_row(
    row: PspProgramRow,
    source_sheet: str,
    *,
    workbook_sheet_titles: Sequence[str] | None = None,
    workbook_path: str | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    status = _normalize_status(row.execution_status)
    label = row.procedure_name
    if row.sheet_ref:
        label = f"{label} ({row.sheet_ref})"

    if status == "empty":
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="execution_status",
                severity=Severity.NEED_REVIEW,
                message=f"程序「{label}」执行状态为空，无法自动判断",
                suggestion="在汇总页补充是否执行，或由 reviewer 人工确认",
                procedure_code="SUMMARY",
                source_sheet=source_sheet,
                source_row=row.source_row,
            )
        )
        return issues

    if status == "partial":
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="execution_status",
                severity=Severity.NEED_REVIEW,
                message=f"程序「{label}」为部分执行，需人工判断证据是否充分",
                suggestion="在底稿中说明部分执行范围及替代程序",
                procedure_code="SUMMARY",
                source_sheet=source_sheet,
                source_row=row.source_row,
            )
        )
        return issues

    if status == "no":
        waiver = (row.waiver_reason or "").strip()
        if not waiver:
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field="waiver_reason",
                    severity=Severity.FAIL,
                    message=f"程序「{label}」标记为不执行，但未填写不执行/拒绝理由",
                    suggestion="在汇总页补充恰当的不执行原因",
                    procedure_code="SUMMARY",
                    source_sheet=source_sheet,
                    source_row=row.source_row,
                )
            )
        elif len(waiver) < _MIN_WAIVER_LEN:
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field="waiver_reason",
                    severity=Severity.WARN,
                    message=f"程序「{label}」不执行理由过短，建议补充充分说明",
                    suggestion="补充与审计准则、项目风险相匹配的拒绝理由",
                    procedure_code="SUMMARY",
                    source_sheet=source_sheet,
                    source_row=row.source_row,
                )
            )
        return issues

    if status == "ambiguous":
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="execution_status",
                severity=Severity.NEED_REVIEW,
                message=f"程序「{label}」执行状态「{row.execution_status}」无法自动解析",
                suggestion="请使用「是/否」或明确的不执行标记，并填写理由",
                procedure_code="SUMMARY",
                source_sheet=source_sheet,
                source_row=row.source_row,
            )
        )

    if status == "yes":
        issues.extend(
            _check_yes_program_sheet(
                row,
                source_sheet,
                workbook_sheet_titles=workbook_sheet_titles,
                workbook_path=workbook_path,
            )
        )

    return issues


def check_psp_completion(
    dataset: SummarySheetDataset,
    *,
    workbook_sheet_titles: Sequence[str] | None = None,
    workbook_path: str | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    if not dataset.programs:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field=None,
                severity=Severity.NEED_REVIEW,
                message="未在底稿中识别到汇总页程序表或表头不匹配",
                suggestion="确认存在「汇总」工作表，且含程序名称与是否执行/不执行原因列",
                procedure_code="SUMMARY",
                source_sheet=dataset.source_sheet or "汇总",
            )
        )
        return issues

    programs = [p for p in dataset.programs if not _should_skip_row(p)]
    targets = [p for p in programs if p.is_psp] or programs

    for row in targets:
        issues.extend(
            _check_program_row(
                row,
                dataset.source_sheet or "汇总",
                workbook_sheet_titles=workbook_sheet_titles,
                workbook_path=workbook_path,
            )
        )

    return issues
