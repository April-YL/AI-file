from rules.psp_sheet_matcher import (
    find_matching_sheet,
    is_likely_internal_sheet,
    ref_query_strings,
)


def test_ref_query_strings_strips_parenthetical():
    assert ref_query_strings("K.01 后推（自动生成）") == [
        "K.01 后推（自动生成）",
        "K.01 后推",
    ]


def test_find_matching_sheet_suffix_and_substring():
    title, score, reason = find_matching_sheet("K.01", ["K.01 后推-2024"])
    assert title == "K.01 后推-2024"
    assert score >= 0.85
    assert reason == "substring"


def test_find_matching_sheet_fuzzy_mid_confidence():
    title, score, reason = find_matching_sheet("K.02.1 细节测试", ["K.02 新增"])
    assert title == "K.02 新增"
    assert 0.48 <= score < 0.72
    assert reason == "fuzzy_ratio"


def test_find_matching_sheet_no_match():
    assert find_matching_sheet("K.99.9", ["K.01", "Lead"])[0] is None


def test_internal_sheet_names_skipped_for_matching():
    assert is_likely_internal_sheet("~internal")
    public, score, _reason = find_matching_sheet("K.01", ["~hidden", "K.01 底稿"])
    assert public == "K.01 底稿"
    assert score >= 0.85
