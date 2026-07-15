from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ingest.workbook_context import load_workbook_context
from report.pipeline import run_workbook_qc_from_path
from rules.how_coverage_diagnostics import OBSERVATION_EVIDENCE_LEVEL
from rules.registry import iter_implemented
from rules.rule_execution_coverage import (
    EXECUTION_DELIVERY_CONTEXT_MISSING,
    EXECUTION_EXECUTED,
    EXECUTION_LLM_DISABLED,
    EXECUTION_NOT_APPLICABLE,
    EXECUTION_NOT_TRIGGERED_BY_CONTEXT,
    EXECUTION_NOT_WIRED,
    EXECUTION_UNKNOWN,
    HOW_EVIDENCE_LEVEL,
    HOW_MISSING,
    HOW_NOT_APPLICABLE,
    build_rule_execution_coverage_matrix,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _evidence_observation() -> dict:
    return {
        "checked_data": [],
        "check_logic": "Checked source values.",
        "expected_result": "Expected values to agree.",
        "actual_result": "Values agreed.",
        "result_summary": "No finding.",
    }


def test_matrix_classifies_ledger_rows_and_missing_how():
    ledger = {
        "items": [
            {
                "rule_id": "fa_list_required_fields",
                "status": "EXECUTED",
                "finding_count": 0,
                "observation": _evidence_observation(),
            },
            {
                "rule_id": "unique_asset_id",
                "status": "EXECUTED",
                "finding_count": 0,
            },
            {
                "rule_id": "asset_value_consistency",
                "status": "NOT_APPLICABLE",
                "finding_count": 0,
                "status_note": "not applicable in this test",
                "observation": _evidence_observation(),
            },
        ]
    }

    matrix = build_rule_execution_coverage_matrix(
        ledger,
        runner_rule_ids=[
            "fa_list_required_fields",
            "unique_asset_id",
            "asset_value_consistency",
        ],
    )
    rows = {row["rule_id"]: row for row in matrix["rules"]}

    assert rows["fa_list_required_fields"]["execution_status"] == EXECUTION_EXECUTED
    assert rows["fa_list_required_fields"]["how_status"] == HOW_EVIDENCE_LEVEL
    assert rows["unique_asset_id"]["execution_status"] == EXECUTION_EXECUTED
    assert rows["unique_asset_id"]["how_status"] == HOW_MISSING
    assert rows["asset_value_consistency"]["execution_status"] == EXECUTION_NOT_APPLICABLE
    assert matrix["summary"]["ledger_status_counts"] == {
        "EXECUTED": 2,
        "NOT_APPLICABLE": 1,
    }


def test_matrix_rows_include_audit_readable_fields_and_dynamic_summary():
    ledger = {
        "items": [
            {
                "rule_id": "fa_list_required_fields",
                "status": "EXECUTED",
                "finding_count": 1,
                "observation": {
                    "checked_data": [
                        {
                            "sheet": "FA list",
                            "section": "资产清单",
                            "location": "A1:D20",
                            "values_read": [
                                {
                                    "label": "资产编号",
                                    "value": "FA-TEST-001",
                                    "cell": "A2",
                                }
                            ],
                        }
                    ],
                    "check_logic": "检查资产编号是否为空。",
                    "expected_result": "资产编号应完整。",
                    "actual_result": "发现 1 条为空。",
                    "result_summary": "触发 finding。",
                },
            },
            {
                "rule_id": "unique_asset_id",
                "status": "DATA_INSUFFICIENT",
                "finding_count": 0,
                "status_note": "缺少 FA list。",
            },
        ]
    }

    matrix = build_rule_execution_coverage_matrix(
        ledger,
        runner_rule_ids=["fa_list_required_fields", "unique_asset_id"],
    )
    rows = {row["rule_id"]: row for row in matrix["rules"]}
    row = rows["fa_list_required_fields"]

    assert row["rule_code"]
    assert row["execution_status_label"] == "已执行"
    assert row["finding_count"] == 1
    assert row["source_summary"] == "FA list / 资产清单"
    assert row["trace_label"] == "可查看取数与判断说明"
    assert row["trace_detail"]["checked_materials"] == ["FA list / 资产清单"]
    assert row["trace_detail"]["source_locations"] == ["FA list!A1:D20"]
    assert row["trace_detail"]["values_read"][0]["cell"] == "A2"
    assert rows["unique_asset_id"]["execution_status_label"] == "资料不足，未能完整执行"
    assert rows["unique_asset_id"]["non_execution_reason"] == "缺少 FA list。"

    actual_counts = {}
    for matrix_row in matrix["rules"]:
        status = matrix_row["execution_status"]
        actual_counts[status] = actual_counts.get(status, 0) + 1
    assert matrix["summary"]["execution_status_counts"] == actual_counts


def test_matrix_explains_llm_disabled_delivery_missing_not_wired_and_unknown():
    ctx = SimpleNamespace(fa_list=object())

    matrix = build_rule_execution_coverage_matrix(
        {"items": []},
        workbook_context=ctx,
        llm_enabled=False,
        delivery_context=None,
        runner_rule_ids=[
            "fa_list_required_fields",
            "addition_semantic_review",
            "first_delivery_standard",
        ],
    )
    rows = {row["rule_id"]: row for row in matrix["rules"]}

    assert rows["addition_semantic_review"]["execution_status"] == EXECUTION_LLM_DISABLED
    assert rows["addition_semantic_review"]["how_status"] == HOW_NOT_APPLICABLE
    assert rows["first_delivery_standard"]["execution_status"] == EXECUTION_DELIVERY_CONTEXT_MISSING
    assert rows["fa_list_required_fields"]["execution_status"] == EXECUTION_UNKNOWN

    not_wired = build_rule_execution_coverage_matrix(
        {"items": []},
        runner_rule_ids=[],
    )
    not_wired_rows = {row["rule_id"]: row for row in not_wired["rules"]}
    assert not_wired_rows["fa_list_required_fields"]["execution_status"] == EXECUTION_NOT_WIRED


def test_matrix_explains_not_triggered_by_context():
    ctx = SimpleNamespace(
        fa_list=None,
        summary=None,
        lead=None,
        rollforward=None,
        addition_list=None,
        addition_test=None,
        addition_sample_output=None,
        disposal_list=None,
        disposal_test=None,
        disposal_sample_output=None,
        disposal_execution_path=None,
        k03_sheets=[],
    )

    matrix = build_rule_execution_coverage_matrix(
        {"items": []},
        workbook_context=ctx,
        runner_rule_ids=[
            "rollforward_exists",
            "addition_required_fields",
            "disposal_sample_match",
            "k03_policy_three_elements_complete",
        ],
    )
    rows = {row["rule_id"]: row for row in matrix["rules"]}

    assert rows["rollforward_exists"]["execution_status"] == EXECUTION_NOT_TRIGGERED_BY_CONTEXT
    assert rows["addition_required_fields"]["execution_status"] == EXECUTION_NOT_TRIGGERED_BY_CONTEXT
    assert rows["disposal_sample_match"]["execution_status"] == EXECUTION_NOT_TRIGGERED_BY_CONTEXT
    assert rows["k03_policy_three_elements_complete"]["execution_status"] == EXECUTION_NOT_TRIGGERED_BY_CONTEXT


def test_current_fixture_matrix_contains_all_implemented_rules_and_no_executed_how_gap():
    path = FIXTURES / "workbook_with_lead.xlsx"
    ctx = load_workbook_context(path)
    report = run_workbook_qc_from_path(str(path), llm=False)

    matrix = build_rule_execution_coverage_matrix(
        report.execution_ledger,
        workbook_context=ctx,
        llm_enabled=False,
    )
    rows = {row["rule_id"]: row for row in matrix["rules"]}
    implemented_ids = {spec.rule_id for spec in iter_implemented()}

    assert implemented_ids.issubset(rows)
    assert matrix["summary"]["matrix_category_counts"] == {
            "implemented_rules": 102,
        "delivery_checks": 2,
        "runtime_guardrails": 1,
    }
    assert matrix["summary"]["implemented_rule_count"] == 102
    assert matrix["summary"]["delivery_check_ids"] == [
        "final_delivery_standard",
        "first_delivery_standard",
    ]
    assert matrix["summary"]["runtime_guardrail_ids"] == ["lead_ingest_readability"]
    assert rows["first_delivery_standard"]["matrix_category"] == "delivery_checks"
    assert rows["final_delivery_standard"]["matrix_category"] == "delivery_checks"
    assert rows["lead_ingest_readability"]["matrix_category"] == "runtime_guardrails"
    assert rows["fa_list_required_fields"]["matrix_category"] == "implemented_rules"
    assert matrix["summary"]["ledger_recorded_rule_count"] == 82
    assert matrix["summary"]["ledger_status_counts"] == {
        "EXECUTED": 13,
        "DATA_INSUFFICIENT": 44,
        "NOT_APPLICABLE": 25,
    }
    assert matrix["summary"]["ledger_how_status_counts"] == {
        "EVIDENCE_LEVEL": 82,
    }
    assert matrix["summary"]["ledger_legacy_count"] == 0
    assert matrix["summary"]["ledger_missing_how_count"] == 0
    assert rows["rollforward_exists"]["execution_status"] == EXECUTION_NOT_TRIGGERED_BY_CONTEXT
    assert rows["addition_semantic_review"]["execution_status"] == EXECUTION_LLM_DISABLED
    assert rows["first_delivery_standard"]["execution_status"] == EXECUTION_DELIVERY_CONTEXT_MISSING
    assert rows["fa_list_required_fields"]["how_status"] == OBSERVATION_EVIDENCE_LEVEL
