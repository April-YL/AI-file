from types import SimpleNamespace

from ingest.models import (
    EvidenceType,
    FieldEvidence,
    FieldResolutionDecision,
    ResolutionStatus,
)
from rules.models import QcIssue, Severity
from agent.bulk_anomaly_guard import evaluate_bulk_anomaly_guard


def _issue(row: int) -> QcIssue:
    return QcIssue(
        asset_id=f"FA-{row}",
        rule_id="unique_asset_id",
        field="asset_id",
        severity=Severity.FAIL,
        message="duplicate",
        suggestion="review",
        source_sheet="FA list",
        source_row=row,
        source_col=1,
    )


def _context(*, evidence_count: int):
    evidence = [
        FieldEvidence(EvidenceType.HEADER_SEMANTIC, "header"),
        FieldEvidence(EvidenceType.VALUE_TYPE, "text"),
        FieldEvidence(EvidenceType.VALUE_DISTRIBUTION, "distinct"),
    ][:evidence_count]
    decision = FieldResolutionDecision(
        standard_field="asset_id",
        status=ResolutionStatus.RESOLVED,
        evidence=evidence,
    )
    dataset = SimpleNamespace(
        records=[object() for _ in range(40)],
        field_resolutions={"asset_id": decision},
        sheet_resolution=None,
    )
    return SimpleNamespace(fa_list=dataset, addition_list=None, disposal_list=None)


def test_bulk_guard_holds_large_cluster_when_mapping_is_weak():
    report = SimpleNamespace(issues=[_issue(row) for row in range(1, 31)])

    result = evaluate_bulk_anomaly_guard(report, _context(evidence_count=2))

    assert result["disposition"] == "REVIEW_REQUIRED"
    assert result["held_finding_count"] == 30
    assert len(report.issues) == 30


def test_bulk_guard_does_not_suppress_strongly_supported_real_cluster():
    report = SimpleNamespace(issues=[_issue(row) for row in range(1, 31)])

    result = evaluate_bulk_anomaly_guard(report, _context(evidence_count=3))

    assert result["disposition"] == "NORMAL"
    assert len(report.issues) == 30


def test_bulk_guard_does_not_trigger_on_small_population():
    report = SimpleNamespace(issues=[_issue(row) for row in range(1, 21)])
    context = _context(evidence_count=2)
    context.fa_list.records = [object() for _ in range(20)]

    result = evaluate_bulk_anomaly_guard(report, context)

    assert result["disposition"] == "NORMAL"
