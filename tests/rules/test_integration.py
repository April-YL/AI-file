from pathlib import Path

import pytest

from ingest.records import load_fa_list_csv
from report.export_json import run_fa_list_qc
from rules.models import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_mixed_fixture_all_severities():
    dataset = load_fa_list_csv(FIXTURES / "fa_list_mixed.csv")
    report = run_fa_list_qc(dataset)

    severities = {i.severity for i in report.issues}
    assert Severity.FAIL in severities
    assert Severity.WARN in severities

    asset_severities = {a.severity for a in report.asset_results}
    assert Severity.PASS in asset_severities

    assert report.summary.total_records == 6
    assert report.summary.fail_count >= 1
    assert report.summary.warn_count >= 1
    assert report.summary.pass_count >= 1


def test_no_asset_id_fixture_need_review():
    dataset = load_fa_list_csv(FIXTURES / "fa_list_no_asset_id.csv")
    report = run_fa_list_qc(dataset)

    severities = {i.severity for i in report.issues}
    assert Severity.NEED_REVIEW in severities
    assert Severity.FAIL in severities or Severity.WARN in severities


def test_valid_fixture_mostly_pass():
    dataset = load_fa_list_csv(FIXTURES / "fa_list_valid.csv")
    report = run_fa_list_qc(dataset)

    assert report.summary.pass_count == 2
    assert report.summary.overall_severity == Severity.PASS
