from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ingest.models import AssetRecord  # noqa: F401

__all__ = [
    "AssetRecord",
    "AutomationLevel",
    "ColumnContext",
    "QcIssue",
    "Severity",
]


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NEED_REVIEW = "NEED_REVIEW"


class AutomationLevel(str, Enum):
    """规则自动化程度（与规则字典 / Agent 映射一致）。"""

    AUTO_FAIL = "AUTO_FAIL"
    AUTO_WARN = "AUTO_WARN"
    REVIEW = "REVIEW"
    MANUAL_ONLY = "MANUAL_ONLY"


@dataclass
class ColumnContext:
    """已映射的标准字段集合（sheet 级）。"""

    mapped_fields: set[str] = field(default_factory=set)
    source_sheet: str = "FA list"
    procedure_code: str = "FA_LIST"


@dataclass
class QcIssue:
    asset_id: str | None
    rule_id: str
    field: str | None
    severity: Severity
    message: str
    suggestion: str
    procedure_code: str = "FA_LIST"
    source_sheet: str = "FA list"
    source_row: int | None = None
    # 规则字典扩展（见 docs/rule-dictionary-mapping.md）
    dict_rule_code: str | None = None
    rule_name: str | None = None
    problem_category: str | None = None
    reviewer_role: str | None = None
    qc_checkpoint: str | None = None
    automation_level: str | None = None
    k1_checklist_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "asset_id": self.asset_id,
            "procedure_code": self.procedure_code,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
            "rule_id": self.rule_id,
            "field": self.field,
            "severity": self.severity.value,
            "message": self.message,
            "suggestion": self.suggestion,
        }
        optional = {
            "dict_rule_code": self.dict_rule_code,
            "rule_name": self.rule_name,
            "problem_category": self.problem_category,
            "reviewer_role": self.reviewer_role,
            "qc_checkpoint": self.qc_checkpoint,
            "automation_level": self.automation_level,
            "k1_checklist_ref": self.k1_checklist_ref,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value
        return data
