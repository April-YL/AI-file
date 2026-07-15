from ingest.fa_list_population import build_fa_list_population
from ingest.models import (
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
    FieldMapping,
)
from ingest.records import FaListDataset
from ingest.workbook_context import WorkbookQcContext
from report.export_json import run_fa_list_qc
from report.pipeline import run_workbook_qc


def _ambiguous_dataset() -> FaListDataset:
    records = [AssetRecord(asset_id="FA-001", asset_name="设备", original_value="100", accumulated_depreciation="20", net_value="999", source_row=2)]
    amount_basis = FaListAmountBasis(
        status=FaListAmountBasisStatus.AMBIGUOUS,
        conflicts=["multiple amount header candidates"],
    )
    population = build_fa_list_population(records, amount_basis=amount_basis)
    profile = FaListReviewProfile(
        routing=FaListRoutingDecision(
            status=FaListRoutingStatus.CONFIRMED,
            selected_sheet="FA list",
            candidates=["FA list"],
            reason="test",
        ),
        amount_basis=amount_basis,
        population=population,
        identity_basis=FaListIdentityBasis(scope=FaListIdentityScope.ASSET_ID),
        salvage_basis=FaListSalvageBasis(mode=FaListSalvageMode.MISSING),
    )
    return FaListDataset(
        source_file="basis.xlsx",
        source_sheet="FA list",
        mapped_fields=[
            FieldMapping("asset_id", "固定资产编号", 1),
            FieldMapping("asset_name", "固定资产名称", 2),
            FieldMapping("original_value", "原值", 3),
            FieldMapping("accumulated_depreciation", "累计折旧", 4),
            FieldMapping("net_value", "净值", 5),
        ],
        records=records,
        amount_basis=amount_basis,
        fa_profile=profile,
    )


def _assert_amount_rules_are_gated(report) -> None:
    ledger = {item["rule_id"]: item for item in report.execution_ledger["items"]}
    assert ledger["asset_amount_non_negative"]["status"] == "DATA_INSUFFICIENT"
    assert ledger["asset_value_consistency"]["status"] == "DATA_INSUFFICIENT"
    assert len([issue for issue in report.issues if issue.field == "amount_basis"]) == 1


def _empty_dataset() -> FaListDataset:
    basis = FaListAmountBasis(status=FaListAmountBasisStatus.NOT_FOUND)
    population = build_fa_list_population([], amount_basis=basis)
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
    return FaListDataset(
        source_file="empty.xlsx",
        source_sheet="FA list",
        mapped_fields=[],
        records=[],
        amount_basis=basis,
        fa_profile=profile,
    )


def test_export_json_entrypoint_passes_amount_basis():
    _assert_amount_rules_are_gated(run_fa_list_qc(_ambiguous_dataset(), llm=False))


def test_workbook_pipeline_entrypoint_passes_amount_basis():
    dataset = _ambiguous_dataset()
    ctx = WorkbookQcContext(
        source_file="basis.xlsx",
        fa_list=dataset,
        summary=None,
        lead=None,
    )

    _assert_amount_rules_are_gated(run_workbook_qc(ctx, llm=False))


def test_empty_fa_list_is_not_pass_in_both_report_entrypoints():
    standalone = run_fa_list_qc(_empty_dataset(), llm=False)
    assert standalone.summary.overall_severity.value == "NEED_REVIEW"

    dataset = _empty_dataset()
    workbook = run_workbook_qc(
        WorkbookQcContext(
            source_file="empty.xlsx",
            fa_list=dataset,
            summary=None,
            lead=None,
        ),
        llm=False,
    )
    assert workbook.summary.overall_severity.value != "PASS"
