from ingest.models import (
    EvidenceType,
    FieldCandidate,
    FieldEvidence,
    FieldResolutionDecision,
    ResolutionStatus,
)
from rules.models import ColumnContext, ReadinessStatus
from rules.readiness import RuleReadinessSpec, evaluate_rule_readiness
from rules.execution_recorder import RuleExecutionRecorder
from rules.runner import run_fa_list_rules


def _decision(field: str, status: ResolutionStatus, evidence_count: int = 2):
    evidence_types = [
        EvidenceType.HEADER_SEMANTIC,
        EvidenceType.VALUE_TYPE,
        EvidenceType.VALUE_DISTRIBUTION,
    ][:evidence_count]
    candidate = FieldCandidate(
        standard_field=field,
        source_header=field,
        column_index=1,
        evidence=[FieldEvidence(kind, kind.value) for kind in evidence_types],
    )
    return FieldResolutionDecision(
        standard_field=field,
        candidates=[candidate],
        selected_candidate=candidate if status == ResolutionStatus.RESOLVED else None,
        status=status,
        evidence=list(candidate.evidence),
        rejection_reasons=["ambiguous deterministic candidates"]
        if status == ResolutionStatus.AMBIGUOUS
        else [],
    )


def test_readiness_accepts_resolved_field_with_minimum_evidence():
    ctx = ColumnContext(
        mapped_fields={"asset_id"},
        field_resolutions={"asset_id": _decision("asset_id", ResolutionStatus.RESOLVED)},
    )

    result = evaluate_rule_readiness(
        RuleReadinessSpec(
            rule_id="unique_asset_id",
            required_fields=("asset_id",),
            minimum_evidence=2,
        ),
        ctx,
    )

    assert result.status == ReadinessStatus.READY


def test_readiness_blocks_ambiguous_field_without_marking_pass():
    ctx = ColumnContext(
        field_resolutions={"asset_id": _decision("asset_id", ResolutionStatus.AMBIGUOUS)},
    )

    result = evaluate_rule_readiness(
        RuleReadinessSpec(
            rule_id="unique_asset_id",
            required_fields=("asset_id",),
            minimum_evidence=2,
        ),
        ctx,
    )

    assert result.status == ReadinessStatus.DATA_INSUFFICIENT
    assert result.blocking_fields == ["asset_id"]
    assert "AMBIGUOUS" in result.note()


def test_required_fields_rule_can_check_true_missing_but_blocks_invalid_mapping():
    spec = RuleReadinessSpec(
        rule_id="addition_required_fields",
        required_fields=("asset_id", "original_value"),
        minimum_evidence=1,
        block_on_missing=False,
    )

    missing = evaluate_rule_readiness(spec, ColumnContext())
    invalid = evaluate_rule_readiness(
        spec,
        ColumnContext(
            field_resolutions={
                "asset_id": _decision("asset_id", ResolutionStatus.INVALID)
            }
        ),
    )

    assert missing.status == ReadinessStatus.READY
    assert invalid.status == ReadinessStatus.DATA_INSUFFICIENT


def test_readiness_reports_not_applicable_separately():
    result = evaluate_rule_readiness(
        RuleReadinessSpec(rule_id="demo"),
        ColumnContext(),
        applicable=False,
    )

    assert result.status == ReadinessStatus.NOT_APPLICABLE


def test_readiness_blocks_missing_required_dataset():
    result = evaluate_rule_readiness(
        RuleReadinessSpec(rule_id="demo", required_data=("addition_list", "rollforward")),
        ColumnContext(available_data={"addition_list"}),
    )

    assert result.status == ReadinessStatus.DATA_INSUFFICIENT
    assert "rollforward" in result.note()


def test_readiness_blocks_unconfirmed_sheet_identity():
    result = evaluate_rule_readiness(
        RuleReadinessSpec(rule_id="demo", required_sheet_kind="addition_list"),
        ColumnContext(
            sheet_kind="disposal_list",
            sheet_resolution_status="AMBIGUOUS",
        ),
    )

    assert result.status == ReadinessStatus.DATA_INSUFFICIENT
    assert "sheet identity" in result.note()


def test_readiness_blocks_unconfirmed_business_semantics():
    result = evaluate_rule_readiness(
        RuleReadinessSpec(
            rule_id="demo",
            required_semantics=("addition_amount_group",),
        ),
        ColumnContext(semantic_states={}),
    )

    assert result.status == ReadinessStatus.DATA_INSUFFICIENT
    assert "addition_amount_group" in result.note()


def test_ambiguous_asset_id_does_not_produce_deterministic_fail():
    recorder = RuleExecutionRecorder()
    ctx = ColumnContext(
        source_sheet="FA list",
        field_resolutions={
            "asset_id": _decision("asset_id", ResolutionStatus.AMBIGUOUS)
        },
    )

    issues = run_fa_list_rules([], ctx, recorder=recorder)
    ledger = recorder.to_ledger()
    item = next(
        item for item in ledger["items"] if item["rule_id"] == "fa_list_required_fields"
    )

    assert not [issue for issue in issues if issue.severity.value == "FAIL"]
    assert item["status"] == "DATA_INSUFFICIENT"
    assert "asset_id" in item["status_note"]
