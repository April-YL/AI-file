from __future__ import annotations

import re

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.models import QcIssue, Severity

RULE_ID = "psp_completion"

_MIN_WAIVER_LEN = 8

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


def _check_program_row(row: PspProgramRow, source_sheet: str) -> list[QcIssue]:
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

    return issues


def check_psp_completion(dataset: SummarySheetDataset) -> list[QcIssue]:
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
        issues.extend(_check_program_row(row, dataset.source_sheet))

    return issues
