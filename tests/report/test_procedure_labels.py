from report.procedure_labels import group_findings_by_procedure, procedure_label


def test_k02_k03_procedure_labels_are_explicit():
    assert procedure_label("K.02.1") == "K.02.1 新增测试"
    assert procedure_label("K.02.1a") == "K.02.1a 新增选样输出"
    assert procedure_label("K.02.2") == "K.02.2 处置测试"
    assert procedure_label("K.02.2a") == "K.02.2a 处置选样输出"
    assert procedure_label("K.03.1") == "K.03.1 SAP"
    assert procedure_label("K.03.2") == "K.03.2 TOD"
    assert procedure_label("K.03.3") == "K.03.3 折旧政策复核"


def test_k02_k03_findings_do_not_fall_into_other_group():
    issues = [
        {"severity": "FAIL", "procedure_code": "K.02.1"},
        {"severity": "WARN", "procedure_code": "K.02.1a"},
        {"severity": "NEED_REVIEW", "procedure_code": "K.02.2"},
        {"severity": "FAIL", "procedure_code": "K.02.2a"},
        {"severity": "WARN", "procedure_code": "K.03.1"},
        {"severity": "NEED_REVIEW", "procedure_code": "K.03.2"},
        {"severity": "FAIL", "procedure_code": "K.03.3"},
        {"severity": "PASS", "procedure_code": "K.02.1"},
    ]

    groups = group_findings_by_procedure(issues)
    codes = [code for code, _, _ in groups]

    assert codes == [
        "K.02.1",
        "K.02.1a",
        "K.02.2",
        "K.02.2a",
        "K.03.1",
        "K.03.2",
        "K.03.3",
    ]
    assert "_other" not in codes
