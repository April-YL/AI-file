from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RollforwardPeriodRole(str, Enum):
    """K.01 后推表列在时间维度上的语义（用于列完整性规则）。"""

    OPENING = "opening"
    MOVEMENT = "movement"
    ENDING = "ending"
    UNKNOWN = "unknown"


class RollforwardLayoutProfile(str, Enum):
    """K.01 底稿版式（见 docs/planning/k01-workpaper-layouts.md）。"""

    SOP_BKD_MATRIX = "sop_bkd_matrix"
    CATEGORY_DUAL_PERIOD = "category_dual_period"
    HYBRID = "hybrid"
    UNRECOGNIZED = "unrecognized"


class SheetKind(str, Enum):
    FA_LIST = "fa_list"
    ADDITION_LIST = "addition_list"
    DISPOSAL_LIST = "disposal_list"
    DEPRECIATION_TOD = "depreciation_tod"
    DEPRECIATION_TOD_SAMPLE = "depreciation_tod_sample"
    LEAD = "lead"
    ROLLFORWARD = "rollforward"
    SUMMARY = "summary"
    SAP = "sap"
    DEPRECIATION_POLICY = "depreciation_policy"
    UNCLASSIFIED = "unclassified"
    SKIP = "skip"


@dataclass
class AssetRecord:
    """标准化 FA list 行记录（ingest 输出、rules 输入）。"""

    source_row: int | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    asset_category: str | None = None
    start_date: str | None = None
    useful_life_months: str | None = None
    salvage_rate: str | None = None
    original_value: str | None = None
    accumulated_depreciation: str | None = None
    impairment_provision: str | None = None
    net_value: str | None = None
    addition_method: str | None = None

    def identity(self) -> str:
        if self.asset_id and str(self.asset_id).strip():
            return str(self.asset_id).strip()
        if self.asset_name and str(self.asset_name).strip():
            return f"name:{str(self.asset_name).strip()}"
        return f"row:{self.source_row or '?'}"


@dataclass
class FieldMapping:
    standard_field: str
    source_header: str
    column_index: int


@dataclass
class RollforwardColumnBinding:
    """后推表金额列：标准金额口径 + 期初/变动/期末语义 + 源列。"""

    measure: str
    period_role: RollforwardPeriodRole
    column_index: int
    source_header: str


@dataclass
class SheetClassification:
    sheet_name: str
    kind: SheetKind
    confidence: float
    name_score: float
    content_score: float
    name_hint: str | None = None
    header_row: int | None = None
    mapped_fields: list[FieldMapping] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class WorkbookDiagnostic:
    path: str
    sheets: list[SheetClassification] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "errors": self.errors,
            "sheets": [
                {
                    "sheet_name": s.sheet_name,
                    "kind": s.kind.value,
                    "confidence": s.confidence,
                    "name_score": s.name_score,
                    "content_score": s.content_score,
                    "name_hint": s.name_hint,
                    "header_row": s.header_row,
                    "mapped_fields": [
                        {
                            "standard_field": m.standard_field,
                            "source_header": m.source_header,
                            "column_index": m.column_index,
                        }
                        for m in s.mapped_fields
                    ],
                    "missing_required": s.missing_required,
                    "missing_recommended": s.missing_recommended,
                    "unmapped_headers": s.unmapped_headers[:20],
                    "notes": s.notes,
                }
                for s in self.sheets
            ],
        }
