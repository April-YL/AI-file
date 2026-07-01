from rules.how_coverage_diagnostics import (
    OBSERVATION_EVIDENCE_LEVEL,
    OBSERVATION_LEGACY,
    OBSERVATION_MISSING,
    build_how_coverage_diagnostics,
    classify_observation_type,
    default_runner_ledger_rule_ids,
)


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
