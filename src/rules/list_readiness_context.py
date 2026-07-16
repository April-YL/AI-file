from __future__ import annotations

from ingest.models import AmountBusinessRole, AmountGroupStatus, SheetKind
from ingest.records import DisposalListSummary, FaListDataset
from rules.models import ColumnContext


def build_list_column_context(
    dataset: FaListDataset,
    *,
    expected_kind: SheetKind,
    procedure_code: str,
    available_data: set[str],
    disposal_summary: DisposalListSummary | None = None,
) -> ColumnContext:
    decision = dataset.sheet_resolution
    selected_kind = decision.selected_kind.value if decision and decision.selected_kind else expected_kind.value
    resolution_status = decision.status.value if decision else "RESOLVED"
    semantic_states: dict[str, str] = {}
    semantic_key = (
        "addition_amount_group"
        if expected_kind == SheetKind.ADDITION_LIST
        else "disposal_amount_group"
    )
    if _amount_group_confirmed(dataset, expected_kind):
        semantic_states[semantic_key] = "CONFIRMED"
    if expected_kind == SheetKind.DISPOSAL_LIST and disposal_summary is not None:
        semantic_states["disposal_summary"] = "CONFIRMED"
    return ColumnContext(
        mapped_fields={m.standard_field for m in dataset.mapped_fields},
        mapped_headers={m.standard_field: m.source_header for m in dataset.mapped_fields},
        mapped_columns={m.standard_field: m.column_index for m in dataset.mapped_fields},
        field_resolutions=dataset.field_resolutions,
        source_sheet=dataset.source_sheet,
        procedure_code=procedure_code,
        available_data=available_data,
        sheet_kind=selected_kind,
        sheet_resolution_status=resolution_status,
        semantic_states=semantic_states,
        derivatives_current=True,
    )


def _amount_group_confirmed(dataset: FaListDataset, expected_kind: SheetKind) -> bool:
    group = next(
        (
            item
            for item in dataset.amount_groups
            if item.group_id == dataset.selected_amount_group_id
        ),
        None,
    )
    if group is None or group.status != AmountGroupStatus.CONFIRMED:
        return False
    expected_role = (
        AmountBusinessRole.ADDITION
        if expected_kind == SheetKind.ADDITION_LIST
        else AmountBusinessRole.DISPOSAL
    )
    return group.business_role in {expected_role, AmountBusinessRole.BALANCE}
