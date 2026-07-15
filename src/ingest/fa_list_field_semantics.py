from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from ingest.models import (
    FaListAmountBasis,
    FaListAmountBasisStatus,
    FaListIdentityBasis,
    FaListIdentityScope,
    FaListPopulationProfile,
    FaListRoutingDecision,
    FaListSalvageBasis,
    FaListSalvageMode,
    FieldMapping,
)

_AMBIGUOUS_SALVAGE_HEADERS = {"残值", "预计残值"}
_CURRENCY_FORMAT_TOKENS = ("¥", "$", "€", "£", "rmb", "cny", "usd")


def resolve_fa_list_identity_basis(
    population: FaListPopulationProfile,
    mapped_fields: list[FieldMapping],
    routing: FaListRoutingDecision,
) -> FaListIdentityBasis:
    asset_id_mapping = next(
        (item for item in mapped_fields if item.standard_field == "asset_id"),
        None,
    )
    asset_name_mapping = next(
        (item for item in mapped_fields if item.standard_field == "asset_name"),
        None,
    )
    entity_mapping = next(
        (item for item in mapped_fields if item.standard_field == "entity_name"),
        None,
    )
    asset_records = population.asset_records
    missing_asset_ids = [
        record.source_row for record in asset_records if not _norm(record.asset_id)
    ]
    entities = {
        _norm(record.entity_name)
        for record in asset_records
        if getattr(record, "entity_name", None) not in (None, "")
    }
    missing_entities = [
        record.source_row for record in asset_records if not _norm(record.entity_name)
    ]
    common = dict(
        asset_id_column=asset_id_mapping.column_index if asset_id_mapping else None,
        asset_name_column=asset_name_mapping.column_index if asset_name_mapping else None,
        entity_column=entity_mapping.column_index if entity_mapping else None,
        missing_asset_id_rows=[row for row in missing_asset_ids if row is not None],
        missing_entity_rows=[row for row in missing_entities if row is not None],
    )
    if not asset_id_mapping or missing_asset_ids:
        return FaListIdentityBasis(
            scope=FaListIdentityScope.UNRESOLVED,
            conflicts=["asset id key is missing or incomplete"],
            **common,
        )
    consolidated = _looks_consolidated(routing.selected_sheet)
    if entity_mapping and (len(entities) > 1 or consolidated):
        if missing_entities:
            return FaListIdentityBasis(
                scope=FaListIdentityScope.UNRESOLVED,
                conflicts=["entity key is incomplete for a consolidated or multi-entity FA list"],
                **common,
            )
        return FaListIdentityBasis(
            scope=FaListIdentityScope.ENTITY_ASSET_ID,
            evidence=[f"complete entity key found in column {entity_mapping.column_index}"],
            **common,
        )
    if consolidated and not entity_mapping:
        return FaListIdentityBasis(
            scope=FaListIdentityScope.UNRESOLVED,
            conflicts=["consolidated FA list has no reliable entity column"],
            **common,
        )
    return FaListIdentityBasis(
        scope=FaListIdentityScope.ASSET_ID,
        evidence=["single-entity asset id scope"],
        **common,
    )


def resolve_fa_list_salvage_basis(
    *,
    header_cells: list[tuple[int, str]],
    rows: list[tuple[Any, ...]],
    header_row: int | None,
    mapped_fields: list[FieldMapping],
    amount_basis: FaListAmountBasis | None,
    number_formats: dict[int, list[str]] | None = None,
) -> FaListSalvageBasis:
    rate_mapping = next(
        (item for item in mapped_fields if item.standard_field == "salvage_rate"),
        None,
    )
    value_mapping = next(
        (item for item in mapped_fields if item.standard_field == "salvage_value"),
        None,
    )
    if rate_mapping and value_mapping:
        if not _original_basis_ready(amount_basis):
            return FaListSalvageBasis(
                mode=FaListSalvageMode.UNRESOLVED,
                rate_column=rate_mapping.column_index,
                value_column=value_mapping.column_index,
                conflicts=["salvage value cannot be cross-checked without confirmed original value"],
            )
        return FaListSalvageBasis(
            mode=FaListSalvageMode.RATE_AND_VALUE,
            rate_column=rate_mapping.column_index,
            value_column=value_mapping.column_index,
            evidence=["explicit salvage rate and salvage value columns coexist"],
        )
    if rate_mapping:
        return FaListSalvageBasis(
            mode=FaListSalvageMode.EXPLICIT_RATE,
            rate_column=rate_mapping.column_index,
            evidence=[f"explicit rate header: {rate_mapping.source_header}"],
        )
    if value_mapping:
        if _original_basis_ready(amount_basis):
            return FaListSalvageBasis(
                mode=FaListSalvageMode.DERIVED_FROM_VALUE,
                value_column=value_mapping.column_index,
                evidence=[f"explicit salvage value header: {value_mapping.source_header}"],
            )
        return FaListSalvageBasis(
            mode=FaListSalvageMode.UNRESOLVED,
            value_column=value_mapping.column_index,
            conflicts=["salvage value exists but original-value basis is not confirmed"],
        )

    ambiguous = [
        (column, text)
        for column, text in header_cells
        if _norm(text) in {_norm(value) for value in _AMBIGUOUS_SALVAGE_HEADERS}
    ]
    if not ambiguous:
        return FaListSalvageBasis(mode=FaListSalvageMode.MISSING)
    if len(ambiguous) > 1:
        return FaListSalvageBasis(
            mode=FaListSalvageMode.UNRESOLVED,
            conflicts=["multiple ambiguous salvage columns"],
        )

    column, header = ambiguous[0]
    formats = (number_formats or {}).get(column, [])
    values = _column_values(rows, column, header_row, amount_basis)
    numeric_values = [value for value in (_decimal(item) for item in values) if value is not None]
    if not numeric_values:
        return FaListSalvageBasis(
            mode=FaListSalvageMode.UNRESOLVED,
            conflicts=["ambiguous salvage column has no numeric evidence"],
        )
    if _has_percent_format(formats) and not _has_currency_format(formats):
        return FaListSalvageBasis(
            mode=FaListSalvageMode.EXPLICIT_RATE,
            rate_column=column,
            evidence=[f"ambiguous header {header} resolved by percentage number format"],
        )
    if all(Decimal("0") <= value <= Decimal("1") for value in numeric_values) and not _has_currency_format(formats):
        return FaListSalvageBasis(
            mode=FaListSalvageMode.EXPLICIT_RATE,
            rate_column=column,
            evidence=[f"ambiguous header {header} resolved by consistent 0-1 distribution"],
        )
    if _original_basis_ready(amount_basis) and _values_form_valid_residual_ratios(
        rows, column, amount_basis, header_row
    ):
        return FaListSalvageBasis(
            mode=FaListSalvageMode.DERIVED_FROM_VALUE,
            value_column=column,
            evidence=[f"ambiguous header {header} resolved as value by relation to original value"],
        )
    return FaListSalvageBasis(
        mode=FaListSalvageMode.UNRESOLVED,
        conflicts=["ambiguous salvage header has conflicting format/distribution evidence"],
    )


def _column_values(
    rows: list[tuple[Any, ...]],
    column: int,
    header_row: int | None,
    basis: FaListAmountBasis | None,
) -> list[Any]:
    start = basis.data_start_row if basis and basis.data_start_row else (header_row or 0) + 1
    end = basis.data_end_row if basis and basis.data_end_row else len(rows)
    return [
        rows[row_no - 1][column - 1]
        for row_no in range(max(start, 1), min(end, len(rows)) + 1)
        if column <= len(rows[row_no - 1])
    ]


def _values_form_valid_residual_ratios(
    rows: list[tuple[Any, ...]],
    salvage_column: int,
    basis: FaListAmountBasis,
    header_row: int | None,
) -> bool:
    original_column = basis.bindings.get("original_value")
    if original_column is None:
        return False
    start = basis.data_start_row or (header_row or 0) + 1
    end = basis.data_end_row or len(rows)
    ratios: list[Decimal] = []
    for row_no in range(max(start, 1), min(end, len(rows)) + 1):
        row = rows[row_no - 1]
        if max(original_column, salvage_column) > len(row):
            continue
        original = _decimal(row[original_column - 1])
        salvage = _decimal(row[salvage_column - 1])
        if original in (None, Decimal("0")) or salvage is None:
            continue
        ratios.append(salvage / original)
    return bool(ratios) and all(Decimal("0") <= ratio <= Decimal("1") for ratio in ratios)


def _original_basis_ready(basis: FaListAmountBasis | None) -> bool:
    return bool(
        basis
        and basis.status == FaListAmountBasisStatus.CONFIRMED
        and "original_value" in basis.bindings
    )


def _has_percent_format(formats: list[str]) -> bool:
    return any("%" in str(value) for value in formats if value)


def _has_currency_format(formats: list[str]) -> bool:
    return any(
        token in str(value).lower()
        for value in formats
        for token in _CURRENCY_FORMAT_TOKENS
        if value
    )


def _decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() in {"", "-", "—"}:
        return None
    text = str(value).strip().replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _looks_consolidated(sheet_name: str | None) -> bool:
    normalized = _norm(sheet_name)
    return any(token in normalized for token in ("汇总", "合并", "consol", "group"))


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()
