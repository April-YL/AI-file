from types import SimpleNamespace

from report.export_annotated_workbook import _finding_issues
from rules.models import QcIssue, Severity


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


def test_review_required_cluster_is_aggregated_only_for_external_delivery():
    raw = [_issue(row) for row in range(1, 31)]
    report = SimpleNamespace(
        issues=raw,
        runtime_timings={
            "delivery_guard": {
                "disposition": "REVIEW_REQUIRED",
                "clusters": [
                    {
                        "finding_count": 30,
                        "dominant_field": "asset_id",
                        "dominant_source_col": 1,
                        "held_issue_indexes": list(range(30)),
                    }
                ],
            }
        },
    )

    delivered = _finding_issues(report)

    assert len(raw) == 30
    assert len(delivered) == 1
    assert delivered[0].severity == Severity.NEED_REVIEW
    assert delivered[0].review_source == "交付止损"
