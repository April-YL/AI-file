from ingest.models import AssetRecord
from ingest.records import load_fa_list_csv
from pathlib import Path

from report.export_json import run_fa_list_qc
from rules.models import Severity
from rules.registry import (
    AgentPriority,
    all_specs,
    ImplementationStatus,
    attach_rule_metadata,
    get_by_dict_code,
    get_by_rule_id,
    iter_implemented,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_get_by_rule_id_fa_list_implemented():
    spec = get_by_rule_id("fa_list_required_fields")
    assert spec is not None
    assert spec.dict_code == "FA-RC-001"
    assert spec.implementation == ImplementationStatus.IMPLEMENTED
    assert spec.agent_priority == AgentPriority.P1


def test_get_by_dict_code_ae001():
    spec = get_by_dict_code("AE-001")
    assert spec is not None
    assert spec.rule_id == "materiality_consistency"


def test_iter_implemented_includes_fa_and_psp_rules():
    ids = {s.rule_id for s in iter_implemented()}
    assert "lead_required_fields" in ids
    assert "lead_tt_overall_min" in ids
    assert "unexpected_movement_investigation" in ids
    assert "lead_rollforward_tb_reconciliation" in ids
    assert "rollforward_exists" in ids
    assert "rollforward_columns_complete" in ids
    assert "fa_list_required_fields" in ids
    assert "psp_completion" in ids


def test_get_by_dict_code_ae003_implemented():
    spec = get_by_dict_code("AE-003")
    assert spec is not None
    assert spec.rule_id == "psp_completion"
    assert spec.implementation == ImplementationStatus.IMPLEMENTED


def test_k03_sap_parameter_rules_are_registered():
    expected = {
        "sap_te_consistency": "DP-SAP-001",
        "sap_high_cra_consistency": "DP-SAP-002",
        "sap_medium_category_deviation_explanation": "DP-SAP-003",
        "sap_high_category_deviation_explanation": "DP-SAP-004",
    }
    for rule_id, dict_code in expected.items():
        spec = get_by_rule_id(rule_id)
        assert spec is not None
        assert spec.dict_code == dict_code
        assert spec.implementation == ImplementationStatus.IMPLEMENTED


def test_attach_rule_metadata_on_issue():
    from rules.models import QcIssue

    issue = QcIssue(
        asset_id="FA-TEST-001",
        rule_id="unique_asset_id",
        field="asset_id",
        severity=Severity.FAIL,
        message="重复",
        suggestion="修正",
    )
    attach_rule_metadata([issue])
    assert issue.dict_rule_code == "FA-RC-002"
    assert issue.rule_name == "资产编号唯一"
    assert issue.automation_level == "AUTO_FAIL"


def test_integration_report_issues_have_dict_metadata():
    dataset = load_fa_list_csv(FIXTURES / "fa_list_mixed.csv")
    report = run_fa_list_qc(dataset)
    fail_issues = [i for i in report.issues if i.severity == Severity.FAIL]
    assert fail_issues
    assert all(i.dict_rule_code for i in fail_issues)
    payload = fail_issues[0].to_dict()
    assert "dict_rule_code" in payload
    assert "rule_name" in payload


def test_registry_contains_current_k03_and_addition_semantic_rule_codes():
    expected = {
        "addition_semantic_review": "AT-LLM-001",
        "k03_program_execution_consistency": "DP-CTRL-001",
        "k03_depreciation_path_identified": "DP-CTRL-002",
        "k03_path_combination_consistency": "DP-CTRL-003",
        "k03_tod_by_item_detail_unreadable": "DP-BI-PRE-001",
        "k03_tod_by_item_required_fields": "DP-BI-PRE-002",
        "k03_tod_by_item_difference_column": "DP-BI-PRE-003",
        "k03_tod_by_item_sad_unavailable": "DP-BI-PRE-004",
        "k03_tod_by_item_difference_over_sad": "DP-BI-001",
        "k03_tod_by_item_total_difference_over_sad": "DP-BI-002",
        "k03_tod_by_item_conclusion_missing": "DP-BI-003",
        "k03_tod_by_item_rollforward_depreciation": "DP-BI-004",
        "k03_policy_sheet_missing": "DP-POL-PRE-001",
        "k03_policy_table_unreadable": "DP-POL-PRE-002",
        "k03_policy_change_without_explanation": "DP-POL-001",
        "k03_policy_obvious_anomaly": "DP-POL-002",
        "k03_policy_sections_incomplete": "DP-POL-003",
        "k03_policy_fa_life_out_of_range": "DP-POL-004",
        "k03_policy_fa_salvage_mismatch": "DP-POL-005",
        "k03_policy_fa_unit_or_category_review": "DP-POL-006",
        "k03_policy_difference_marker": "DP-POL-007",
        "k03_tod_sampling_output_required": "DP-TOD-PRE-001",
        "k03_tod_sampling_currency": "DP-TOD-001",
        "k03_tod_sampling_te_consistency": "DP-TOD-002",
        "k03_tod_sampling_population_reconciliation": "DP-TOD-003",
        "k03_tod_sampling_count_consistency": "DP-TOD-004",
        "k03_tod_sampling_identity_consistency": "DP-TOD-005",
        "k03_tod_sampling_attributes": "DP-TOD-006",
        "k03_tod_sampling_difference_followup": "DP-TOD-007",
        "k03_tod_sampling_documentation": "DP-TOD-008",
    }
    for rule_id, dict_code in expected.items():
        spec = get_by_rule_id(rule_id)
        assert spec is not None
        assert spec.dict_code == dict_code
        assert spec.implementation == ImplementationStatus.IMPLEMENTED




def test_registry_display_metadata_has_no_question_mark_corruption():
    display_fields = ("rule_name", "qc_checkpoint", "problem_category", "k1_ref", "notes")
    for spec in all_specs():
        for field in display_fields:
            value = getattr(spec, field)
            if value is None:
                continue
            text = str(value)
            assert "??" not in text, f"{spec.rule_id}.{field} contains mojibake: {text}"
        for hint in spec.sheet_hints:
            assert "??" not in hint, f"{spec.rule_id}.sheet_hints contains mojibake: {hint}"


def test_registry_rule_names_are_readable_static_metadata():
    for spec in all_specs():
        name = str(spec.rule_name or "").strip()
        assert name, f"{spec.rule_id} rule_name is empty"
        assert name != spec.rule_id, f"{spec.rule_id} rule_name duplicates rule_id"
        assert name != spec.dict_code, f"{spec.rule_id} rule_name duplicates dict_code"


def test_registry_locks_current_k03_display_names():
    expected_names = {
        "k03_policy_table_unreadable": "\u6298\u65e7\u653f\u7b56\u8868\u8bfb\u53d6\u8d28\u91cf",
        "k03_policy_fa_life_out_of_range": "FA list \u4f7f\u7528\u5bff\u547d\u4e0e\u653f\u7b56\u8303\u56f4",
        "k03_tod_by_item_difference_over_sad": "by-item \u6298\u65e7\u5dee\u5f02\u8d85\u8fc7 SAD",
        "k03_tod_by_item_rollforward_depreciation": "by-item \u6298\u65e7\u4e0e K.01 \u540e\u63a8\u52fe\u7a3d",
    }
    for rule_id, expected_name in expected_names.items():
        spec = get_by_rule_id(rule_id)
        assert spec is not None
        assert spec.rule_name == expected_name
