from ingest.models import AssetRecord
from ingest.records import load_fa_list_csv
from pathlib import Path

from report.export_json import run_fa_list_qc
from rules.models import Severity
from rules.registry import (
    AgentPriority,
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
    assert ids == {
        "fa_list_required_fields",
        "unique_asset_id",
        "asset_value_consistency",
        "asset_amount_non_negative",
        "useful_life_positive",
        "salvage_rate_range",
        "psp_completion",
        "materiality_consistency",
        "risk_threshold_consistency",
    }


def test_get_by_dict_code_ae003_implemented():
    spec = get_by_dict_code("AE-003")
    assert spec is not None
    assert spec.rule_id == "psp_completion"
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
