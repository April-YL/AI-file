from ingest.sheet_classifier import classify_sheet, score_by_name
from ingest.models import SheetKind


def test_name_variants_fa_list():
    k, s, _ = score_by_name("K.01.1a FA list")
    assert k == SheetKind.FA_LIST
    assert s >= 0.8

    k2, _, _ = score_by_name("FA list-24")
    assert k2 == SheetKind.FA_LIST


def test_name_addition_list():
    k, s, _ = score_by_name("K.02.1b 新增清单")
    assert k == SheetKind.ADDITION_LIST
    assert s >= 0.8


def test_name_disposal_list_variants():
    k, s, _ = score_by_name("K.02.2b 处置清单")
    assert k == SheetKind.DISPOSAL_LIST
    assert s >= 0.8

    k2, s2, _ = score_by_name("K.02.2b 减少清单")
    assert k2 == SheetKind.DISPOSAL_LIST
    assert s2 >= 0.8


def test_skip_internal():
    k, _, _ = score_by_name("DS_INTERNAL_DOCUMENT_STORAGE")
    assert k == SheetKind.SKIP


def test_fa_list_name_wins_over_rollforward_content():
    rows = [
        ("固定资产编号", "原值", "累计折旧", "净值"),
        ("FA-TEST-001", 1000, 100, 900),
    ]
    kind, confidence, *_ = classify_sheet("FA list", rows)
    assert kind == SheetKind.FA_LIST
    assert confidence >= 0.85


def test_addition_list_name_wins_over_rollforward_content():
    rows = [
        ("固定资产编号", "固定资产名称", "原值", "新增方式"),
        ("FA-TEST-001", "设备A", 1000, "购置"),
    ]
    kind, confidence, *_ = classify_sheet("新增清单", rows)
    assert kind == SheetKind.ADDITION_LIST
    assert confidence >= 0.85


def test_disposal_list_name_wins_over_rollforward_content():
    rows = [
        ("固定资产编号", "原值", "累计折旧", "净值", "处置日期", "处置方式"),
        ("FA-TEST-001", 1000, 100, 900, "2025-01-01", "报废"),
    ]
    kind, confidence, *_ = classify_sheet("处置清单", rows)
    assert kind == SheetKind.DISPOSAL_LIST
    assert confidence >= 0.85


def test_summary_name_wins_over_rollforward_content():
    rows = [
        ("程序", "工作表", "是否执行", "原值", "累计折旧", "净值"),
        ("K.01", "K.01", "是", 100, 10, 90),
    ]
    kind, confidence, *_ = classify_sheet("汇总 ", rows)
    assert kind == SheetKind.SUMMARY
    assert confidence >= 0.75


def test_lead_name_wins_over_rollforward_content():
    rows = [
        ("客户名称", "测试客户"),
        ("名义金额 (SAD)", "5000"),
        ("可容忍误差 (TE)", "100000"),
    ]
    kind, confidence, *_ = classify_sheet("K.00 Lead Sheet", rows)
    assert kind == SheetKind.LEAD
    assert confidence >= 0.7


def test_name_rollforward_houtui():
    k, s, _ = score_by_name("固定资产后推表")
    assert k == SheetKind.ROLLFORWARD
    assert s >= 0.85


def test_period_headers_favor_rollforward_on_unnamed_sheet():
    rows = [
        (
            "固定资产编号",
            "固定资产名称",
            "期初原值",
            "期末原值",
            "期初累计折旧",
            "期末累计折旧",
            "期末净值",
        ),
        ("FA-TEST-001", "设备A", 100, 120, 30, 36, 84),
    ]
    kind, *_ = classify_sheet("Sheet1", rows)
    assert kind == SheetKind.ROLLFORWARD
