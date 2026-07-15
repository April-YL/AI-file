from ingest.fa_list_field_semantics import (
    resolve_fa_list_identity_basis,
    resolve_fa_list_salvage_basis,
)
from ingest.fa_list_population import build_fa_list_population
from ingest.fa_list_routing import choose_fa_list_route
from ingest.field_mapping import map_headers
from ingest.models import (
    AmountCurrencyRole,
    AmountPeriodRole,
    AssetRecord,
    FaListAmountBasis,
    FaListAmountBasisSource,
    FaListAmountBasisStatus,
    FaListIdentityScope,
    FaListPopulationStatus,
    FaListRoutingStatus,
    FaListSalvageMode,
    FieldMapping,
    SheetKind,
)


def _confirmed_basis() -> FaListAmountBasis:
    return FaListAmountBasis(
        status=FaListAmountBasisStatus.CONFIRMED,
        source=FaListAmountBasisSource.K01_FORMULA,
        bindings={
            "original_value": 3,
            "accumulated_depreciation": 4,
            "impairment_provision": 5,
            "net_value": 6,
        },
        category_column=2,
        data_start_row=2,
        data_end_row=5,
        period_role=AmountPeriodRole.ENDING,
        currency_role=AmountCurrencyRole.REPORTING,
    )


def test_fa_routing_prefers_unique_summary_and_records_reason():
    decision = choose_fa_list_route(["FA list -US", "FA list-汇总"])

    assert decision.status == FaListRoutingStatus.CONFIRMED
    assert decision.selected_sheet == "FA list-汇总"
    assert decision.candidates == ["FA list -US", "FA list-汇总"]
    assert "consolidated" in decision.reason


def test_multiple_summary_candidates_stop_instead_of_using_order():
    decision = choose_fa_list_route(["FA list-汇总", "FA list Consol"])

    assert decision.status == FaListRoutingStatus.AMBIGUOUS
    assert decision.selected_sheet is None


def test_population_keeps_missing_identity_amount_row_and_separates_structural_rows():
    records = [
        AssetRecord(source_row=2, asset_id="FA-001", original_value="100", accumulated_depreciation="20", net_value="80"),
        AssetRecord(source_row=3, original_value="50", accumulated_depreciation="10", net_value="40"),
        AssetRecord(source_row=4, asset_name="尾差", impairment_provision="-0.01", net_value="0.01"),
        AssetRecord(source_row=5, asset_name="期末余额", original_value="150", accumulated_depreciation="30", net_value="120"),
    ]

    profile = build_fa_list_population(records, amount_basis=_confirmed_basis())

    assert profile.status == FaListPopulationStatus.READY
    assert [record.source_row for record in profile.asset_records] == [2]
    assert [record.source_row for record in profile.identity_incomplete_records] == [3]
    assert [record.source_row for record in profile.reconciliation_records] == [2, 3, 4]
    roles = {item.record.source_row: item.role.value for item in profile.classified_rows}
    assert roles[3] == "identity_incomplete_detail"
    assert roles[4] == "adjustment_detail"
    assert roles[5] == "aggregate_or_note"


def test_population_blocks_confirmed_scope_that_excludes_asset_row():
    records = [
        AssetRecord(source_row=2, asset_id="FA-001", original_value="100", accumulated_depreciation="20", net_value="80"),
        AssetRecord(source_row=6, asset_id="FA-002", original_value="50", accumulated_depreciation="10", net_value="40"),
    ]

    profile = build_fa_list_population(records, amount_basis=_confirmed_basis())

    assert profile.status == FaListPopulationStatus.SCOPE_UNRESOLVED
    assert profile.outside_basis_rows == [6]


def test_company_scope_uses_entity_plus_asset_id_only_for_multi_entity_list():
    routing = choose_fa_list_route(["FA list-汇总"])
    mappings = [FieldMapping("entity_name", "公司", 1), FieldMapping("asset_id", "资产编号", 2)]
    records = [
        AssetRecord(entity_name="A公司", asset_id="001"),
        AssetRecord(entity_name="B公司", asset_id="001"),
    ]

    population = build_fa_list_population(records, amount_basis=_confirmed_basis())
    basis = resolve_fa_list_identity_basis(population, mappings, routing)

    assert basis.scope == FaListIdentityScope.ENTITY_ASSET_ID
    assert basis.entity_column == 1


def test_consolidated_identity_scope_stops_when_entity_is_missing():
    routing = choose_fa_list_route(["FA list-汇总"])
    mappings = [FieldMapping("entity_name", "公司", 1), FieldMapping("asset_id", "资产编号", 2)]
    records = [
        AssetRecord(source_row=2, entity_name="A公司", asset_id="001"),
        AssetRecord(source_row=3, entity_name=None, asset_id="002"),
    ]
    population = build_fa_list_population(records, amount_basis=_confirmed_basis())

    basis = resolve_fa_list_identity_basis(population, mappings, routing)

    assert basis.scope == FaListIdentityScope.UNRESOLVED
    assert basis.missing_entity_rows == [3]


def test_identity_scope_stops_without_asset_id_mapping():
    routing = choose_fa_list_route(["FA list"])
    records = [AssetRecord(source_row=2, asset_name="设备A")]
    population = build_fa_list_population(records, amount_basis=_confirmed_basis())

    basis = resolve_fa_list_identity_basis(population, [], routing)

    assert basis.scope == FaListIdentityScope.UNRESOLVED


def test_structural_label_conflicting_with_identity_stops_population():
    records = [AssetRecord(source_row=2, entity_name="合计", asset_id="001", original_value="100")]

    profile = build_fa_list_population(records, amount_basis=_confirmed_basis())

    assert profile.status == FaListPopulationStatus.SCOPE_UNRESOLVED
    assert profile.classified_rows[0].role.value == "unresolved"


def test_salvage_headers_are_split_between_rate_and_value():
    mapped, _ = map_headers(
        [(1, "残值率(%)"), (2, "净残值"), (3, "原值")],
        sheet_kind=SheetKind.FA_LIST,
    )

    assert {(item.standard_field, item.column_index) for item in mapped} >= {
        ("salvage_rate", 1),
        ("salvage_value", 2),
    }


def test_explicit_salvage_rate_and_value_can_coexist():
    mappings = [
        FieldMapping("salvage_rate", "残值率", 2),
        FieldMapping("salvage_value", "净残值", 3),
    ]

    basis = resolve_fa_list_salvage_basis(
        header_cells=[(2, "残值率"), (3, "净残值")],
        rows=[("资产编号", "残值率", "净残值")],
        header_row=1,
        mapped_fields=mappings,
        amount_basis=_confirmed_basis(),
    )

    assert basis.mode == FaListSalvageMode.RATE_AND_VALUE
    assert (basis.rate_column, basis.value_column) == (2, 3)


def test_explicit_route_must_exist_in_candidates():
    decision = choose_fa_list_route(["FA list"], explicit_sheet="missing")

    assert decision.status == FaListRoutingStatus.NOT_FOUND


def test_ambiguous_salvage_header_uses_distribution_or_stops():
    basis = _confirmed_basis()
    rate = resolve_fa_list_salvage_basis(
        header_cells=[(1, "资产编号"), (2, "残值")],
        rows=[("资产编号", "残值"), ("A", 0.05), ("B", 0.03)],
        header_row=1,
        mapped_fields=[],
        amount_basis=basis,
    )
    mixed = resolve_fa_list_salvage_basis(
        header_cells=[(1, "资产编号"), (2, "残值")],
        rows=[("资产编号", "残值"), ("A", 0.05), ("B", 5000)],
        header_row=1,
        mapped_fields=[],
        amount_basis=basis,
    )

    assert rate.mode == FaListSalvageMode.EXPLICIT_RATE
    assert rate.rate_column == 2
    assert mixed.mode == FaListSalvageMode.UNRESOLVED
