from report.ui_app import _classify_finding_bucket_v2


def test_fa_list_findings_are_other_even_when_fail_and_amount_related():
    issue = {
        "procedure_code": "FA_LIST",
        "rule_id": "asset_value_consistency",
        "severity": "FAIL",
        "message": "净值与原值、累计折旧勾稽不一致。",
        "qc_checkpoint": "Y-审计基础程序",
    }

    assert _classify_finding_bucket_v2(issue) == "other"


def test_mapping_n_or_no_checkpoints_are_prompt_items():
    issue = {
        "procedure_code": "K.03.3",
        "rule_id": "k03_policy_fa_life_out_of_range",
        "severity": "FAIL",
        "message": "资产寿命与政策范围不一致。",
        "qc_checkpoint": "No-非PSP程序要求",
    }

    assert _classify_finding_bucket_v2(issue) == "other"


def test_by_item_sad_difference_is_not_high_priority():
    issue = {
        "procedure_code": "K.03.2",
        "rule_id": "k03_tod_by_item_difference_over_sad",
        "severity": "FAIL",
        "message": "K.03.2 by-item 折旧差异超过 SAD。",
        "qc_checkpoint": "Y-错报风险-假设不是所有底稿都涉及",
    }

    assert _classify_finding_bucket_v2(issue) == "other"


def test_by_item_need_review_stays_manual():
    issue = {
        "procedure_code": "K.03.2",
        "rule_id": "k03_tod_by_item_conclusion_missing",
        "severity": "NEED_REVIEW",
        "message": "折旧测试说明记录缺失，需要人工复核。",
        "qc_checkpoint": "Y-错报风险-假设不是所有底稿都涉及",
    }

    assert _classify_finding_bucket_v2(issue) == "manual"


def test_core_reconciliation_rule_remains_high_priority():
    issue = {
        "procedure_code": "K.01",
        "rule_id": "rollforward_fa_list_reconciliation",
        "severity": "FAIL",
        "message": "K.01 后推与 FA list 期末数不一致。",
        "qc_checkpoint": "Y-审计基础程序",
    }

    assert _classify_finding_bucket_v2(issue) == "high"
