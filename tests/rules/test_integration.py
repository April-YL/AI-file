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


def test_fa_list_rules_record_evidence_how_for_all_rules():
    dataset = load_fa_list_csv(FIXTURES / "fa_list_mixed.csv")
    report = run_fa_list_qc(dataset)

    items = {item["rule_id"]: item for item in report.execution_ledger["items"]}
    for rule_id in (
        "fa_list_required_fields",
        "unique_asset_id",
        "asset_value_consistency",
        "asset_amount_non_negative",
        "useful_life_positive",
        "salvage_rate_range",
    ):
        observation = items[rule_id]["observation"]
        assert set(observation) == {
            "checked_data",
            "check_logic",
            "expected_result",
            "actual_result",
            "result_summary",
        }
        assert observation["checked_data"]
        assert "finding" in observation["result_summary"]
        if items[rule_id]["finding_count"]:
            assert str(items[rule_id]["finding_count"]) in observation["result_summary"]
        else:
            assert "未触发" in observation["result_summary"]


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
