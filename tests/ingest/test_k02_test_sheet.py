from ingest.k02_test_sheet import (
    extract_limited_execution_note_from_rows,
    find_k02_test_sheet_title,
)


def test_find_disposal_test_sheet_title():
    titles = ["汇总", "处置清单", "K.02.2 处置测试", "K.02.2a 处置选样输出"]
    assert find_k02_test_sheet_title(titles, kind="disposal") == "K.02.2 处置测试"


def test_extract_limited_execution_note_from_rows():
    rows = [
        ("K.02.2：详细测试 (处置/报废)",),
        ("样本总体",),
        ("本期处置资产净值小于TE，未执行抽样测试",),
    ]
    note = extract_limited_execution_note_from_rows(rows)
    assert note is not None
    assert "小于TE" in note


def test_extract_returns_none_for_generic_text():
    rows = [("我们将本年固定资产购置增加的明细作为测试的样本总体。",)]
    assert extract_limited_execution_note_from_rows(rows) is None
