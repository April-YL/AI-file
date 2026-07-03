from rules.how_coverage_diagnostics import (
    OBSERVATION_EVIDENCE_LEVEL,
    OBSERVATION_LEGACY,
    OBSERVATION_MISSING,
    build_how_coverage_diagnostics,
    classify_observation_type,
    default_runner_ledger_rule_ids,
)
from pathlib import Path

from report.pipeline import run_workbook_qc_from_path
from rules.execution_recorder import RuleExecutionRecorder
from rules.k03_runner import run_k03_rules


K03_LOW_RISK_RULE_IDS = {
    "k03_policy_sheet_missing",
    "k03_policy_table_unreadable",
    "k03_policy_sections_incomplete",
    "k03_tod_by_item_detail_unreadable",
    "k03_tod_by_item_required_fields",
    "k03_tod_by_item_sad_unavailable",
    "k03_tod_by_item_difference_column",
    "k03_tod_by_item_difference_over_sad",
    "k03_tod_by_item_total_difference_over_sad",
    "k03_tod_by_item_rollforward_depreciation",
    "k03_tod_by_item_conclusion_missing",
    "k03_policy_fa_life_out_of_range",
    "k03_policy_fa_salvage_mismatch",
    "k03_policy_fa_unit_or_category_review",
    "k03_policy_difference_marker",
    "k03_policy_change_without_explanation",
    "k03_policy_obvious_anomaly",
}

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _evidence_observation() -> dict:
    return {
        "checked_data": [],
        "check_logic": "Checked source values.",
        "expected_result": "Expected values to agree.",
        "actual_result": "Values agreed.",
        "result_summary": "No finding.",
    }


def _legacy_observation() -> dict:
    return {
        "path": "primary",
        "inputs": [],
        "checks": [],
        "notes": [],
    }


def test_classify_observation_type_uses_fixed_key_sets():
    assert classify_observation_type(_evidence_observation()) == OBSERVATION_EVIDENCE_LEVEL
    assert classify_observation_type(_legacy_observation()) == OBSERVATION_LEGACY
    assert classify_observation_type(None) == OBSERVATION_MISSING


def test_build_how_coverage_diagnostics_summarizes_ledger_observation_coverage():
    ledger = {
        "items": [
            {
                "rule_id": "fa_list_required_fields",
                "status": "EXECUTED",
                "finding_count": 1,
                "status_note": "",
                "observation": _evidence_observation(),
            },
            {
                "rule_id": "unique_asset_id",
                "status": "EXECUTED",
                "finding_count": 0,
                "status_note": "",
                "observation": _legacy_observation(),
            },
            {
                "rule_id": "asset_value_consistency",
                "status": "EXECUTED",
                "finding_count": 2,
                "status_note": "",
            },
            {
                "rule_id": "lead_required_fields",
                "status": "DATA_INSUFFICIENT",
                "finding_count": 0,
                "status_note": "missing lead",
            },
            {
                "rule_id": "rollforward_exists",
                "status": "NOT_APPLICABLE",
                "finding_count": 0,
                "status_note": "not applicable",
            },
        ]
    }

    diagnostics = build_how_coverage_diagnostics(
        ledger,
        runner_rule_ids=[
            "fa_list_required_fields",
            "unique_asset_id",
            "asset_value_consistency",
            "lead_required_fields",
            "rollforward_exists",
            "psp_completion",
        ],
    )

    assert diagnostics["summary"]["ledger_recorded_rule_count"] == 5
    assert diagnostics["summary"]["rules_with_observation_count"] == 2
    assert diagnostics["summary"]["evidence_level_how_count"] == 1
    assert diagnostics["summary"]["legacy_observation_count"] == 1
    assert diagnostics["summary"]["missing_observation_count"] == 3

    rows = {row["rule_id"]: row for row in diagnostics["rules"]}
    assert rows["fa_list_required_fields"]["next_action"] == "DONE"
    assert rows["fa_list_required_fields"]["module"] == "FA list"
    assert rows["unique_asset_id"]["next_action"] == "NEED_HOW"
    assert rows["asset_value_consistency"]["observation_type"] == "MISSING"
    assert rows["lead_required_fields"]["next_action"] == "DATA_INSUFFICIENT"
    assert rows["rollforward_exists"]["next_action"] == "NOT_EXECUTED"
    assert rows["psp_completion"]["execution_status"] is None
    assert rows["psp_completion"]["next_action"] == "NOT_EXECUTED"
    assert rows["psp_completion"]["module"] == "PSP"


def test_default_runner_ledger_rule_ids_include_existing_runner_and_pipeline_rules():
    rule_ids = set(default_runner_ledger_rule_ids())

    assert "fa_list_required_fields" in rule_ids
    assert "psp_completion" in rule_ids
    assert "lead_required_fields" in rule_ids
    assert "lead_ingest_readability" in rule_ids
    assert "rollforward_fa_list_reconciliation" in rule_ids


def test_k03_missing_dataset_records_low_risk_evidence_how():
    recorder = RuleExecutionRecorder()

    run_k03_rules(None, recorder=recorder)

    diagnostics = build_how_coverage_diagnostics(recorder.to_ledger())
    rows = {row["rule_id"]: row for row in diagnostics["rules"]}
    for rule_id in K03_LOW_RISK_RULE_IDS:
        assert rows[rule_id]["observation_type"] == OBSERVATION_EVIDENCE_LEVEL
        assert rows[rule_id]["next_action"] == "DATA_INSUFFICIENT"


def test_k03_current_fixture_reaches_first_batch_how_coverage():
    report = run_workbook_qc_from_path(str(FIXTURES / "workbook_with_lead.xlsx"), llm=False)

    diagnostics = build_how_coverage_diagnostics(report.execution_ledger)
    k03_rows = [row for row in diagnostics["rules"] if row["module"] == "K.03"]
    evidence_rows = [
        row
        for row in k03_rows
        if row["observation_type"] == OBSERVATION_EVIDENCE_LEVEL
    ]

    assert len(k03_rows) == 17
    assert {row["rule_id"] for row in evidence_rows} == K03_LOW_RISK_RULE_IDS
