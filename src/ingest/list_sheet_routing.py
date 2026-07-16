"""Safe workbook-level routing for FA, addition, and disposal lists.

The generic classifier owns per-sheet identity evidence.  This module only
decides whether one of those already-classified candidates is safe to adopt as
the primary dataset for a list role.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ingest.models import ResolutionStatus, SheetKind, SheetResolutionDecision
from ingest.sheet_period_routing import sheet_period_sort_key
from ingest.workbook_structure import WorkbookStructure


LIST_SHEET_KINDS = frozenset(
    {SheetKind.FA_LIST, SheetKind.ADDITION_LIST, SheetKind.DISPOSAL_LIST}
)


@dataclass(frozen=True)
class ListSheetRouteDecision:
    target_kind: SheetKind
    status: ResolutionStatus
    selected_sheet: str | None = None
    candidates: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    candidate_decisions: dict[str, SheetResolutionDecision] = field(default_factory=dict)

    @property
    def confirmed(self) -> bool:
        return self.status == ResolutionStatus.RESOLVED and bool(self.selected_sheet)


def resolve_list_sheet_route(
    structure: WorkbookStructure,
    target_kind: SheetKind,
    *,
    explicit_sheet: str | None = None,
    confidence_margin: float = 0.12,
) -> ListSheetRouteDecision:
    """Select a primary list only when the existing identity evidence is decisive."""
    if target_kind not in LIST_SHEET_KINDS:
        raise ValueError(f"unsupported list sheet kind: {target_kind.value}")

    candidate_decisions = {
        name: decision
        for name, decision in structure.sheet_resolutions.items()
        if _decision_mentions(decision, target_kind)
    }
    resolved = [
        decision
        for decision in candidate_decisions.values()
        if decision.status == ResolutionStatus.RESOLVED
        and decision.selected_kind == target_kind
    ]

    if explicit_sheet:
        decision = structure.sheet_resolutions.get(explicit_sheet)
        if decision is None:
            return ListSheetRouteDecision(
                target_kind,
                ResolutionStatus.INVALID,
                candidates=tuple(candidate_decisions),
                reasons=(f"explicit sheet does not exist or was not scanned: {explicit_sheet}",),
                candidate_decisions=candidate_decisions,
            )
        if decision.status == ResolutionStatus.RESOLVED and decision.selected_kind == target_kind:
            return ListSheetRouteDecision(
                target_kind,
                ResolutionStatus.RESOLVED,
                selected_sheet=explicit_sheet,
                candidates=(explicit_sheet,),
                reasons=("explicit sheet passed the same identity gate",),
                candidate_decisions={explicit_sheet: decision},
            )
        return ListSheetRouteDecision(
            target_kind,
            ResolutionStatus.AMBIGUOUS,
            candidates=tuple(candidate_decisions),
            reasons=(
                f"explicit sheet is not resolved as {target_kind.value}: {explicit_sheet}",
                *decision.rejection_reasons,
            ),
            candidate_decisions=candidate_decisions,
        )

    if not resolved:
        status = ResolutionStatus.AMBIGUOUS if candidate_decisions else ResolutionStatus.MISSING
        reasons = (
            (f"candidate sheets exist but none is resolved as {target_kind.value}",)
            if candidate_decisions
            else (f"no candidate sheet for {target_kind.value}",)
        )
        return ListSheetRouteDecision(
            target_kind,
            status,
            candidates=tuple(candidate_decisions),
            reasons=reasons,
            candidate_decisions=candidate_decisions,
        )

    ordered = sorted(
        resolved,
        key=lambda decision: sheet_period_sort_key(
            decision.sheet_name,
            confidence=_selected_confidence(decision, target_kind),
            source_path=Path(structure.source_file),
        ),
    )
    if len(ordered) == 1:
        selected = ordered[0]
        return ListSheetRouteDecision(
            target_kind,
            ResolutionStatus.RESOLVED,
            selected_sheet=selected.sheet_name,
            candidates=(selected.sheet_name,),
            reasons=("single resolved candidate",),
            candidate_decisions={selected.sheet_name: selected},
        )

    first, second = ordered[:2]
    first_key = sheet_period_sort_key(
        first.sheet_name,
        confidence=_selected_confidence(first, target_kind),
        source_path=Path(structure.source_file),
    )
    second_key = sheet_period_sort_key(
        second.sheet_name,
        confidence=_selected_confidence(second, target_kind),
        source_path=Path(structure.source_file),
    )
    period_is_decisive = first_key[0] < second_key[0]
    confidence_gap = _selected_confidence(first, target_kind) - _selected_confidence(
        second, target_kind
    )
    if period_is_decisive or confidence_gap >= confidence_margin:
        reason = (
            "current-period candidate outranks prior/stub candidates"
            if period_is_decisive
            else f"top candidate confidence margin is {confidence_gap:.2f}"
        )
        return ListSheetRouteDecision(
            target_kind,
            ResolutionStatus.RESOLVED,
            selected_sheet=first.sheet_name,
            candidates=tuple(item.sheet_name for item in ordered),
            reasons=(reason,),
            candidate_decisions={item.sheet_name: item for item in ordered},
        )

    return ListSheetRouteDecision(
        target_kind,
        ResolutionStatus.AMBIGUOUS,
        candidates=tuple(item.sheet_name for item in ordered),
        reasons=(
            "multiple same-period list candidates cannot be distinguished safely",
            f"top confidence gap {confidence_gap:.2f} is below {confidence_margin:.2f}",
        ),
        candidate_decisions={item.sheet_name: item for item in ordered},
    )


def _decision_mentions(decision: SheetResolutionDecision, target_kind: SheetKind) -> bool:
    return decision.selected_kind == target_kind or any(
        kind == target_kind for kind, _score in decision.candidates
    )


def _selected_confidence(
    decision: SheetResolutionDecision,
    target_kind: SheetKind,
) -> float:
    return max(
        (score for kind, score in decision.candidates if kind == target_kind),
        default=0.0,
    )
