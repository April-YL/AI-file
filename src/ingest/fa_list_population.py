from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Iterable

from ingest.models import (
    AssetRecord,
    ClassifiedFaRow,
    FaListAmountBasis,
    FaListAmountBasisStatus,
    FaListPopulationProfile,
    FaListPopulationStatus,
    FaListRowRole,
)

_ADJUSTMENT_LABELS = {"尾差", "调整", "调整项", "重分类", "资产类别重分类"}
_AGGREGATE_LABELS = {
    "合计",
    "总计",
    "小计",
    "期初余额",
    "期末余额",
    "年初余额",
    "年末余额",
    "notes",
    "note",
    "说明",
}


def build_fa_list_population(
    records: list[AssetRecord],
    *,
    amount_basis: FaListAmountBasis | None,
) -> FaListPopulationProfile:
    # The parser creates one record for every non-empty source row. Preserve
    # rows that contain only unmapped values so the population remains auditable.
    nonempty = [
        record
        for record in records
        if record.source_row is not None or not _record_empty(record)
    ]
    if not nonempty:
        return FaListPopulationProfile(
            status=FaListPopulationStatus.EMPTY,
            scanned_nonempty_rows=0,
            reasons=["FA list has headers but no non-empty population rows"],
        )

    classified: list[ClassifiedFaRow] = []
    outside_basis_rows: list[int] = []
    for record in nonempty:
        role, reasons = _classify_row(record)
        include_asset = role == FaListRowRole.ASSET_DETAIL
        include_reconciliation = role in {
            FaListRowRole.ASSET_DETAIL,
            FaListRowRole.IDENTITY_INCOMPLETE_DETAIL,
            FaListRowRole.ADJUSTMENT_DETAIL,
        }
        if include_reconciliation and _outside_confirmed_range(record, amount_basis):
            outside_basis_rows.append(record.source_row or 0)
            reasons = [*reasons, "row with asset/amount evidence is outside confirmed formula range"]
        classified.append(
            ClassifiedFaRow(
                record=record,
                role=role,
                reasons=reasons,
                include_in_asset_rules=include_asset,
                include_in_reconciliation=include_reconciliation,
            )
        )

    asset_records = [item.record for item in classified if item.include_in_asset_rules]
    identity_incomplete_records = [
        item.record
        for item in classified
        if item.role == FaListRowRole.IDENTITY_INCOMPLETE_DETAIL
    ]
    reconciliation_records = [
        item.record for item in classified if item.include_in_reconciliation
    ]
    excluded = [item for item in classified if not item.include_in_asset_rules]
    has_unresolved = any(item.role == FaListRowRole.UNRESOLVED for item in classified)
    if outside_basis_rows or has_unresolved:
        status = FaListPopulationStatus.SCOPE_UNRESOLVED
        reasons = [
            "population contains unresolved structural conflicts"
            if has_unresolved
            else "confirmed formula range excludes rows with asset/amount evidence"
        ]
    elif not asset_records:
        status = FaListPopulationStatus.EMPTY
        reasons = ["no asset detail or identity-incomplete detail rows"]
    else:
        status = FaListPopulationStatus.READY
        reasons = []
    return FaListPopulationProfile(
        status=status,
        classified_rows=classified,
        asset_records=asset_records,
        identity_incomplete_records=identity_incomplete_records,
        reconciliation_records=reconciliation_records,
        excluded_rows=excluded,
        scanned_nonempty_rows=len(nonempty),
        outside_basis_rows=sorted(row for row in outside_basis_rows if row),
        reasons=reasons,
    )


def _classify_row(record: AssetRecord) -> tuple[FaListRowRole, list[str]]:
    labels = _row_labels(record)
    adjustment_label = _matches_label(labels, _ADJUSTMENT_LABELS)
    aggregate_label = _matches_label(labels, _AGGREGATE_LABELS)
    structural_labels = {_norm(value) for value in _ADJUSTMENT_LABELS | _AGGREGATE_LABELS}
    has_asset_id = not _is_blank(record.asset_id) and _norm(record.asset_id) not in structural_labels
    has_asset_name = not _is_blank(record.asset_name) and _norm(record.asset_name) not in structural_labels
    if (adjustment_label or aggregate_label) and (has_asset_id or has_asset_name):
        return FaListRowRole.UNRESOLVED, ["structural label conflicts with asset identity"]
    if adjustment_label and not (has_asset_id or has_asset_name):
        return FaListRowRole.ADJUSTMENT_DETAIL, ["structural adjustment label without credible asset identity"]
    if aggregate_label and not (has_asset_id or has_asset_name):
        return FaListRowRole.AGGREGATE_OR_NOTE, ["aggregate/note label without credible asset identity"]
    if has_asset_id or has_asset_name:
        return FaListRowRole.ASSET_DETAIL, ["asset id or non-structural asset name present"]
    if _has_amount_evidence(record):
        return FaListRowRole.IDENTITY_INCOMPLETE_DETAIL, ["amount evidence present but identity missing"]
    return FaListRowRole.AGGREGATE_OR_NOTE, ["non-empty row has no asset identity or amount evidence"]


def _record_empty(record: AssetRecord) -> bool:
    return all(
        _is_blank(getattr(record, field))
        for field in (
            "asset_id",
            "asset_name",
            "asset_category",
            "entity_name",
            "currency",
            "start_date",
            "useful_life_months",
            "salvage_rate",
            "salvage_value",
            "original_value",
            "accumulated_depreciation",
            "impairment_provision",
            "net_value",
        )
    )


def _has_amount_evidence(record: AssetRecord) -> bool:
    return any(
        _parse_amount(getattr(record, field)) is not None
        for field in (
            "original_value",
            "accumulated_depreciation",
            "impairment_provision",
            "net_value",
            "salvage_value",
        )
        if not _is_blank(getattr(record, field))
    )


def _row_labels(record: AssetRecord) -> list[str]:
    return [
        _norm(value)
        for value in (
            record.asset_id,
            record.asset_name,
            record.asset_category,
            record.entity_name,
            record.currency,
        )
        if not _is_blank(value)
    ]


def _matches_label(labels: Iterable[str], candidates: set[str]) -> bool:
    normalized_candidates = {_norm(value) for value in candidates}
    return any(label in normalized_candidates for label in labels)


def _outside_confirmed_range(
    record: AssetRecord,
    basis: FaListAmountBasis | None,
) -> bool:
    if (
        basis is None
        or basis.status != FaListAmountBasisStatus.CONFIRMED
        or basis.data_start_row is None
        or basis.data_end_row is None
        or record.source_row is None
    ):
        return False
    return not (basis.data_start_row <= record.source_row <= basis.data_end_row)


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() in {"", "-", "—"}


def _parse_amount(value: object) -> Decimal | None:
    if _is_blank(value):
        return None
    text = str(value).strip().replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None
