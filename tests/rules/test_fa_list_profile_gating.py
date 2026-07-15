from ingest.models import (
    FaListAmountBasis,
    FaListAmountBasisStatus,
    FaListIdentityBasis,
    FaListIdentityScope,
    FaListPopulationProfile,
    FaListPopulationStatus,
    FaListReviewProfile,
    FaListRoutingDecision,
    FaListRoutingStatus,
    FaListSalvageBasis,
    FaListSalvageMode,
)
from rules.execution_recorder import RuleExecutionRecorder
from rules.models import ColumnContext
from rules.runner import FA_LIST_RULE_IDS, run_fa_list_rules


def test_empty_fa_population_marks_every_rule_data_insufficient():
    profile = FaListReviewProfile(
        routing=FaListRoutingDecision(
            status=FaListRoutingStatus.CONFIRMED,
            selected_sheet="FA list",
            candidates=["FA list"],
            reason="single candidate",
        ),
        amount_basis=FaListAmountBasis(status=FaListAmountBasisStatus.NOT_FOUND),
        population=FaListPopulationProfile(
            status=FaListPopulationStatus.EMPTY,
            reasons=["no asset detail rows"],
        ),
        identity_basis=FaListIdentityBasis(scope=FaListIdentityScope.UNRESOLVED),
        salvage_basis=FaListSalvageBasis(mode=FaListSalvageMode.MISSING),
    )
    recorder = RuleExecutionRecorder()

    issues = run_fa_list_rules(
        [],
        ColumnContext(source_sheet="FA list", procedure_code="FA_LIST"),
        recorder=recorder,
        profile=profile,
    )

    assert len(issues) == 1
    assert issues[0].field == "population"
    ledger = {item["rule_id"]: item for item in recorder.to_ledger()["items"]}
    assert set(ledger) == set(FA_LIST_RULE_IDS)
    assert ledger["fa_list_required_fields"]["status"] == "EXECUTED"
    assert ledger["fa_list_required_fields"]["finding_count"] == 1
    assert all(ledger[rule_id]["status"] == "DATA_INSUFFICIENT" for rule_id in FA_LIST_RULE_IDS[1:])
