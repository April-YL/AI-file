from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ingest.models import AssetRecord  # noqa: F401

__all__ = ["AssetRecord", "ColumnContext", "QcIssue", "Severity"]


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NEED_REVIEW = "NEED_REVIEW"


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

    def to_dict(self) -> dict[str, Any]:
        return {
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
