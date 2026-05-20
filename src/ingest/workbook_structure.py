"""整本固定资产底稿结构识别。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ingest.models import SheetClassification, SheetKind, WorkbookDiagnostic
from ingest.workbook_reader import diagnose_workbook

# 标准程序流（与 docs/audit-workflow.md 一致）
PROGRAM_FLOW: tuple[SheetKind, ...] = (
    SheetKind.SUMMARY,
    SheetKind.LEAD,
    SheetKind.ROLLFORWARD,
    SheetKind.FA_LIST,
    SheetKind.ADDITION_LIST,
    SheetKind.DISPOSAL_LIST,
    SheetKind.DEPRECIATION_TOD,
    SheetKind.SAP,
    SheetKind.DEPRECIATION_POLICY,
)

CORE_SHEET_KINDS: frozenset[SheetKind] = frozenset(
    {SheetKind.SUMMARY, SheetKind.LEAD, SheetKind.ROLLFORWARD, SheetKind.FA_LIST}
)


class StructureIssueCode(str, Enum):
    MISSING_CORE_SHEET = "missing_core_sheet"
    DUPLICATE_SHEET_KIND = "duplicate_sheet_kind"
    LOW_CONFIDENCE_SHEET = "low_confidence_sheet"
    UNCLASSIFIED_PROGRAM_SHEET = "unclassified_program_sheet"
    NAME_CONTENT_MISMATCH = "name_content_mismatch"


@dataclass
class StructureIssue:
    code: StructureIssueCode
    message: str
    sheet_kind: str | None = None
    sheet_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "sheet_kind": self.sheet_kind,
            "sheet_name": self.sheet_name,
        }


@dataclass
class WorkbookStructure:
    source_file: str
    sheets_by_kind: dict[str, list[SheetClassification]] = field(default_factory=dict)
    program_flow: list[dict[str, Any]] = field(default_factory=list)
    issues: list[StructureIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "sheets_by_kind": {
                kind: [
                    {
                        "sheet_name": s.sheet_name,
                        "confidence": s.confidence,
                        "header_row": s.header_row,
                        "mapped_field_count": len(s.mapped_fields),
                        "missing_required": s.missing_required,
                    }
                    for s in sheets
                ]
                for kind, sheets in self.sheets_by_kind.items()
            },
            "program_flow": self.program_flow,
            "issues": [i.to_dict() for i in self.issues],
        }


def _group_sheets(diag: WorkbookDiagnostic) -> dict[str, list[SheetClassification]]:
    grouped: dict[str, list[SheetClassification]] = {}
    for sheet in diag.sheets:
        if sheet.kind in (SheetKind.SKIP,):
            continue
        key = sheet.kind.value
        grouped.setdefault(key, []).append(sheet)
    return grouped


def analyze_workbook_structure(
    path: str | Path,
    *,
    max_rows: int = 100,
    confidence_threshold: float = 0.45,
) -> WorkbookStructure:
    path = Path(path)
    diag = diagnose_workbook(path, max_rows=max_rows)
    grouped = _group_sheets(diag)
    issues: list[StructureIssue] = []

    for kind in CORE_SHEET_KINDS:
        if kind.value not in grouped:
            issues.append(
                StructureIssue(
                    code=StructureIssueCode.MISSING_CORE_SHEET,
                    message=f"未识别到核心工作表：{kind.value}",
                    sheet_kind=kind.value,
                )
            )

    for kind, sheets in grouped.items():
        if len(sheets) > 1 and kind in {k.value for k in CORE_SHEET_KINDS}:
            names = ", ".join(s.sheet_name for s in sheets)
            issues.append(
                StructureIssue(
                    code=StructureIssueCode.DUPLICATE_SHEET_KIND,
                    message=f"{kind} 存在 {len(sheets)} 个候选 sheet：{names}",
                    sheet_kind=kind,
                )
            )
        for s in sheets:
            if s.confidence < confidence_threshold:
                issues.append(
                    StructureIssue(
                        code=StructureIssueCode.LOW_CONFIDENCE_SHEET,
                        message=f"识别置信度偏低 ({s.confidence})",
                        sheet_kind=kind,
                        sheet_name=s.sheet_name,
                    )
                )
            for note in s.notes:
                if "name_content_mismatch" in note:
                    issues.append(
                        StructureIssue(
                            code=StructureIssueCode.NAME_CONTENT_MISMATCH,
                            message=note,
                            sheet_kind=kind,
                            sheet_name=s.sheet_name,
                        )
                    )

    for sheet in diag.sheets:
        if sheet.kind == SheetKind.UNCLASSIFIED and sheet.name_score >= 0.7:
            issues.append(
                StructureIssue(
                    code=StructureIssueCode.UNCLASSIFIED_PROGRAM_SHEET,
                    message=f"名称像程序表但未识别类型：{sheet.sheet_name}",
                    sheet_name=sheet.sheet_name,
                )
            )

    program_flow: list[dict[str, Any]] = []
    for kind in PROGRAM_FLOW:
        for sheet in grouped.get(kind.value, []):
            program_flow.append(
                {
                    "kind": kind.value,
                    "sheet_name": sheet.sheet_name,
                    "confidence": sheet.confidence,
                    "header_row": sheet.header_row,
                }
            )

    return WorkbookStructure(
        source_file=str(path),
        sheets_by_kind=grouped,
        program_flow=program_flow,
        issues=issues,
    )
