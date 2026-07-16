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


class AmountPeriodRole(str, Enum):
    OPENING = "opening"
    CURRENT_PERIOD = "current_period"
    ENDING = "ending"
    AS_OF_EVENT = "as_of_event"
    UNKNOWN = "unknown"


class AmountCurrencyRole(str, Enum):
    ORIGINAL = "original"
    REPORTING = "reporting"
    UNKNOWN = "unknown"


class AmountBusinessRole(str, Enum):
    BALANCE = "balance"
    ADDITION = "addition"
    DISPOSAL = "disposal"
    UNKNOWN = "unknown"


class AmountGroupStatus(str, Enum):
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"
    CONFLICTED = "conflicted"
    NOT_FOUND = "not_found"


class FaListAmountBasisStatus(str, Enum):
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"
    NOT_FOUND = "not_found"


class FaListAmountBasisSource(str, Enum):
    K01_FORMULA = "k01_formula"
    FA_SUMMARY_FORMULA = "fa_summary_formula"
    UNIQUE_HEADERS = "unique_headers"


class FaListRoutingStatus(str, Enum):
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class FaListPopulationStatus(str, Enum):
    READY = "ready"
    EMPTY = "empty"
    SCOPE_UNRESOLVED = "scope_unresolved"


class FaListRowRole(str, Enum):
    ASSET_DETAIL = "asset_detail"
    IDENTITY_INCOMPLETE_DETAIL = "identity_incomplete_detail"
    ADJUSTMENT_DETAIL = "adjustment_detail"
    AGGREGATE_OR_NOTE = "aggregate_or_note"
    UNRESOLVED = "unresolved"
    EMPTY_ROW = "empty_row"


class FaListIdentityScope(str, Enum):
    ASSET_ID = "asset_id"
    ENTITY_ASSET_ID = "entity_asset_id"
    UNRESOLVED = "unresolved"


class FaListSalvageMode(str, Enum):
    EXPLICIT_RATE = "explicit_rate"
    DERIVED_FROM_VALUE = "derived_from_value"
    RATE_AND_VALUE = "rate_and_value"
    UNRESOLVED = "unresolved"
    MISSING = "missing"


class SheetKind(str, Enum):
    FA_LIST = "fa_list"
    ADDITION_LIST = "addition_list"
    ADDITION_TEST = "addition_test"
    ADDITION_SAMPLE_OUTPUT = "addition_sample_output"
    DISPOSAL_LIST = "disposal_list"
    DISPOSAL_TEST = "disposal_test"
    DISPOSAL_SAMPLE_OUTPUT = "disposal_sample_output"
    DEPRECIATION_TOD = "depreciation_tod"
    DEPRECIATION_TOD_SAMPLE = "depreciation_tod_sample"
    LEAD = "lead"
    ROLLFORWARD = "rollforward"
    SUMMARY = "summary"
    SAP = "sap"
    DEPRECIATION_POLICY = "depreciation_policy"
    UNCLASSIFIED = "unclassified"
    SKIP = "skip"


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    INVALID = "INVALID"


class EvidenceType(str, Enum):
    HEADER_SEMANTIC = "HEADER_SEMANTIC"
    VALUE_TYPE = "VALUE_TYPE"
    VALUE_DISTRIBUTION = "VALUE_DISTRIBUTION"
    STRUCTURAL_CONTEXT = "STRUCTURAL_CONTEXT"


@dataclass(frozen=True)
class FieldEvidence:
    evidence_type: EvidenceType
    description: str
    source_sheet: str | None = None
    row: int | None = None
    column: int | None = None
    cell_range: str | None = None


@dataclass
class FieldCandidate:
    standard_field: str
    source_header: str
    column_index: int
    evidence: list[FieldEvidence] = field(default_factory=list)
    negative_evidence: list[FieldEvidence] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class FieldResolutionDecision:
    standard_field: str
    candidates: list[FieldCandidate] = field(default_factory=list)
    selected_candidate: FieldCandidate | None = None
    status: ResolutionStatus = ResolutionStatus.MISSING
    evidence: list[FieldEvidence] = field(default_factory=list)
    negative_evidence: list[FieldEvidence] = field(default_factory=list)
    source_sheet: str | None = None
    header: str | None = None
    row: int | None = None
    column: int | None = None
    cell_range: str | None = None
    resolution_source: str = "deterministic"
    acceptance_reason: str = ""
    rejection_reasons: list[str] = field(default_factory=list)
    reorganization_count: int = 0


@dataclass
class SheetResolutionDecision:
    sheet_name: str
    candidates: list[tuple[SheetKind, float]] = field(default_factory=list)
    selected_kind: SheetKind | None = None
    status: ResolutionStatus = ResolutionStatus.MISSING
    evidence: list[FieldEvidence] = field(default_factory=list)
    negative_evidence: list[FieldEvidence] = field(default_factory=list)
    resolution_source: str = "deterministic"
    acceptance_reason: str = ""
    rejection_reasons: list[str] = field(default_factory=list)
    reorganization_count: int = 0


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
    salvage_value: str | None = None
    entity_name: str | None = None
    currency: str | None = None
    original_value: str | None = None
    accumulated_depreciation: str | None = None
    impairment_provision: str | None = None
    net_value: str | None = None
    addition_method: str | None = None
    disposal_date: str | None = None
    disposal_method: str | None = None

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
class FaListAmountBasis:
    status: FaListAmountBasisStatus
    source: FaListAmountBasisSource | None = None
    bindings: dict[str, int] = field(default_factory=dict)
    category_column: int | None = None
    data_start_row: int | None = None
    data_end_row: int | None = None
    evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    period_role: AmountPeriodRole = AmountPeriodRole.UNKNOWN
    currency_role: AmountCurrencyRole = AmountCurrencyRole.UNKNOWN
    criteria_columns: tuple[int, ...] = ()
    currency_values: tuple[str, ...] = ()


@dataclass
class FaListRoutingDecision:
    status: FaListRoutingStatus
    selected_sheet: str | None = None
    candidates: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class ClassifiedFaRow:
    record: AssetRecord
    role: FaListRowRole
    reasons: list[str] = field(default_factory=list)
    include_in_asset_rules: bool = False
    include_in_reconciliation: bool = False


@dataclass
class FaListPopulationProfile:
    status: FaListPopulationStatus
    classified_rows: list[ClassifiedFaRow] = field(default_factory=list)
    asset_records: list[AssetRecord] = field(default_factory=list)
    identity_incomplete_records: list[AssetRecord] = field(default_factory=list)
    reconciliation_records: list[AssetRecord] = field(default_factory=list)
    excluded_rows: list[ClassifiedFaRow] = field(default_factory=list)
    scanned_nonempty_rows: int = 0
    outside_basis_rows: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class FaListIdentityBasis:
    scope: FaListIdentityScope
    asset_id_column: int | None = None
    asset_name_column: int | None = None
    entity_column: int | None = None
    missing_asset_id_rows: list[int] = field(default_factory=list)
    missing_entity_rows: list[int] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class FaListSalvageBasis:
    mode: FaListSalvageMode
    rate_column: int | None = None
    value_column: int | None = None
    evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class FaListReviewProfile:
    routing: FaListRoutingDecision
    amount_basis: FaListAmountBasis
    population: FaListPopulationProfile
    identity_basis: FaListIdentityBasis
    salvage_basis: FaListSalvageBasis


@dataclass(frozen=True)
class AmountColumnCandidate:
    measure: str
    source_header: str
    column_index: int
    period_role: AmountPeriodRole
    currency_role: AmountCurrencyRole
    business_role: AmountBusinessRole
    evidence: tuple[str, ...] = ()


@dataclass
class AmountFieldGroup:
    group_id: str
    members: dict[str, AmountColumnCandidate]
    period_role: AmountPeriodRole
    currency_role: AmountCurrencyRole
    business_role: AmountBusinessRole
    status: AmountGroupStatus
    confidence: float
    reasons: list[str] = field(default_factory=list)
    missing_measures: list[str] = field(default_factory=list)


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
    resolution_decision: SheetResolutionDecision | None = None


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
