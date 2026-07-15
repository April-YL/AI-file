from decimal import Decimal

from ingest.fa_list_population import build_fa_list_population
from ingest.models import (
    AmountCurrencyRole,
    AmountPeriodRole,
    AssetRecord,
    FaListAmountBasis,
    FaListAmountBasisStatus,
    FaListIdentityBasis,
    FaListIdentityScope,
    FaListReviewProfile,
    FaListRoutingDecision,
    FaListRoutingStatus,
    FaListSalvageBasis,
    FaListSalvageMode,
)
from ingest.reconciliation import ReconciliationStatus, run_fa_rollforward_reconciliations
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.models import ColumnContext, Severity
from rules.runner import run_fa_list_rules


def test_unresolved_amount_basis_emits_one_review_and_skips_only_amount_rules():
    records = [
        AssetRecord(
            asset_id="FA-001",
            asset_name="设备",
            original_value="100",
            accumulated_depreciation="20",
            net_value="999",
            useful_life_months="60",
            salvage_rate="0.05",
            source_row=2,
        )
    ]
    ctx = ColumnContext(
        mapped_fields={
            "asset_id",
            "asset_name",
            "original_value",
            "accumulated_depreciation",
            "net_value",
            "useful_life_months",
            "salvage_rate",
        },
        source_sheet="FA list",
        procedure_code="FA_LIST",
    )
    basis = FaListAmountBasis(
        status=FaListAmountBasisStatus.AMBIGUOUS,
        conflicts=["multiple amount header candidates"],
    )
    recorder = RuleExecutionRecorder()

    issues = run_fa_list_rules(records, ctx, recorder=recorder, amount_basis=basis)
    ledger = {item["rule_id"]: item for item in recorder.to_ledger()["items"]}

    basis_issues = [issue for issue in issues if issue.field == "amount_basis"]
    assert len(basis_issues) == 1
    assert basis_issues[0].severity == Severity.NEED_REVIEW
    assert not any(issue.rule_id == "asset_value_consistency" for issue in issues)
    for rule_id in ("asset_amount_non_negative", "asset_value_consistency"):
        assert ledger[rule_id]["status"] == "DATA_INSUFFICIENT"
        assert ledger[rule_id]["finding_count"] == 0
        assert ledger[rule_id]["observation"]["checked_data"][0]["values_read"] == []
    assert ledger["unique_asset_id"]["status"] == "EXECUTED"
    assert ledger["useful_life_positive"]["status"] == "EXECUTED"


def test_confirmed_basis_checks_rows_with_id_or_name_and_excludes_no_identity_rows():
    records = [
        AssetRecord(asset_id="FA-001", asset_name="设备", original_value="100", accumulated_depreciation="20", net_value="999", source_row=2),
        AssetRecord(asset_id=None, asset_name="未编号设备", original_value="-1", accumulated_depreciation="0", impairment_provision="0", net_value="-1", source_row=3),
        AssetRecord(asset_id=None, asset_name=None, original_value=None, accumulated_depreciation=None, impairment_provision="-0.01", net_value="0.01", source_row=4),
    ]
    ctx = ColumnContext(
        mapped_fields={"asset_id", "asset_name", "original_value", "accumulated_depreciation", "impairment_provision", "net_value"},
        source_sheet="FA list",
        procedure_code="FA_LIST",
    )
    basis = FaListAmountBasis(
        status=FaListAmountBasisStatus.CONFIRMED,
        bindings={"original_value": 3, "accumulated_depreciation": 4, "impairment_provision": 5, "net_value": 6},
        data_start_row=2,
        data_end_row=4,
        period_role=AmountPeriodRole.ENDING,
        currency_role=AmountCurrencyRole.REPORTING,
    )
    population = build_fa_list_population(records, amount_basis=basis)
    profile = FaListReviewProfile(
        routing=FaListRoutingDecision(
            status=FaListRoutingStatus.CONFIRMED,
            selected_sheet="FA list",
            candidates=["FA list"],
            reason="test",
        ),
        amount_basis=basis,
        population=population,
        identity_basis=FaListIdentityBasis(scope=FaListIdentityScope.UNRESOLVED),
        salvage_basis=FaListSalvageBasis(mode=FaListSalvageMode.MISSING),
    )

    issues = run_fa_list_rules(population.asset_records, ctx, amount_basis=basis, profile=profile)
    value_issues = [issue for issue in issues if issue.rule_id == "asset_value_consistency"]

    assert len(value_issues) == 1
    assert value_issues[0].asset_id == "FA-001"
    amount_issues = [issue for issue in issues if issue.rule_id == "asset_amount_non_negative"]
    assert amount_issues
    assert {issue.source_row for issue in amount_issues} == {3}


def test_unresolved_basis_disables_only_agent_recalculated_k01_reconciliation():
    basis = FaListAmountBasis(status=FaListAmountBasisStatus.AMBIGUOUS)
    fa_list = FaListDataset(
        source_file="basis.xlsx",
        source_sheet="FA list",
        mapped_fields=[],
        records=[AssetRecord(asset_id="FA-001", net_value="999")],
        amount_basis=basis,
    )
    rollforward = RollforwardSheetDataset(
        source_file="basis.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        ending_totals={"net_value": Decimal("80")},
    )

    checks = run_fa_rollforward_reconciliations(
        fa_list,
        rollforward,
        fields=("net_value",),
    )

    assert len(checks) == 1
    assert checks[0].status == ReconciliationStatus.NOT_APPLICABLE
    assert checks[0].left_value is None
    assert checks[0].right_value == "80"


def test_multi_currency_original_amounts_are_not_summed_for_k01_reconciliation():
    basis = FaListAmountBasis(
        status=FaListAmountBasisStatus.CONFIRMED,
        bindings={"net_value": 5},
        data_start_row=2,
        data_end_row=3,
        period_role=AmountPeriodRole.ENDING,
        currency_role=AmountCurrencyRole.ORIGINAL,
        currency_values=("cny", "usd"),
    )
    fa_list = FaListDataset(
        source_file="multi_currency.xlsx",
        source_sheet="FA list",
        mapped_fields=[],
        records=[
            AssetRecord(asset_id="A", currency="CNY", net_value="100"),
            AssetRecord(asset_id="B", currency="USD", net_value="100"),
        ],
        amount_basis=basis,
    )
    rollforward = RollforwardSheetDataset(
        source_file="multi_currency.xlsx",
        source_sheet="K.01",
        header_row=1,
        mapped_fields=[],
        ending_totals={"net_value": Decimal("200")},
    )

    checks = run_fa_rollforward_reconciliations(fa_list, rollforward, fields=("net_value",))

    assert checks[0].status == ReconciliationStatus.NOT_APPLICABLE
    assert checks[0].left_value is None
