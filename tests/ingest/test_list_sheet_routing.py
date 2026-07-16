from ingest.list_sheet_routing import resolve_list_sheet_route
from ingest.models import ResolutionStatus, SheetKind, SheetResolutionDecision
from ingest.workbook_structure import WorkbookStructure


def _decision(name: str, kind: SheetKind, confidence: float) -> SheetResolutionDecision:
    return SheetResolutionDecision(
        sheet_name=name,
        candidates=[(kind, confidence)],
        selected_kind=kind,
        status=ResolutionStatus.RESOLVED,
        acceptance_reason="test",
    )


def _structure(*decisions: SheetResolutionDecision) -> WorkbookStructure:
    return WorkbookStructure(
        source_file="case20251231.xlsx",
        sheet_resolutions={item.sheet_name: item for item in decisions},
    )


def test_single_resolved_list_candidate_is_selected():
    route = resolve_list_sheet_route(
        _structure(_decision("新增清单", SheetKind.ADDITION_LIST, 0.9)),
        SheetKind.ADDITION_LIST,
    )

    assert route.confirmed
    assert route.selected_sheet == "新增清单"


def test_same_period_close_candidates_are_not_silently_ranked_first():
    route = resolve_list_sheet_route(
        _structure(
            _decision("新增清单A", SheetKind.ADDITION_LIST, 0.90),
            _decision("新增清单B", SheetKind.ADDITION_LIST, 0.85),
        ),
        SheetKind.ADDITION_LIST,
    )

    assert route.status == ResolutionStatus.AMBIGUOUS
    assert route.selected_sheet is None
    assert set(route.candidates) == {"新增清单A", "新增清单B"}


def test_current_period_candidate_outranks_prior_period_copy():
    route = resolve_list_sheet_route(
        _structure(
            _decision("处置清单", SheetKind.DISPOSAL_LIST, 0.9),
            _decision("处置清单-24", SheetKind.DISPOSAL_LIST, 0.95),
        ),
        SheetKind.DISPOSAL_LIST,
    )

    assert route.confirmed
    assert route.selected_sheet == "处置清单"


def test_explicit_sheet_does_not_bypass_identity_gate():
    route = resolve_list_sheet_route(
        _structure(_decision("FA list", SheetKind.FA_LIST, 0.95)),
        SheetKind.ADDITION_LIST,
        explicit_sheet="FA list",
    )

    assert route.status == ResolutionStatus.AMBIGUOUS
    assert route.selected_sheet is None


def test_ambiguous_per_sheet_decision_is_retained_as_candidate_not_selected():
    decision = SheetResolutionDecision(
        sheet_name="资产变动明细",
        candidates=[
            (SheetKind.ADDITION_LIST, 0.8),
            (SheetKind.DISPOSAL_LIST, 0.78),
        ],
        status=ResolutionStatus.AMBIGUOUS,
        rejection_reasons=["name and content disagree"],
    )

    route = resolve_list_sheet_route(
        _structure(decision),
        SheetKind.ADDITION_LIST,
    )

    assert route.status == ResolutionStatus.AMBIGUOUS
    assert route.selected_sheet is None
    assert route.candidates == ("资产变动明细",)
