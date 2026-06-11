from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import openpyxl

from llm.config import LlmConfig
from llm.ingest_review import (
    EXPECTED_INGEST_OBJECTS,
    K01_PROFILE_HINT,
    SYSTEM_PROMPT,
    IngestReviewCandidatePreview,
    IngestReviewPayload,
    build_missing_k01_ingest_review_payload,
    build_ingest_review_user_prompt,
    parse_ingest_review_result,
    run_ingest_review,
    run_workbook_ingest_reviews,
)


def _config(*, enabled: bool = True) -> LlmConfig:
    return LlmConfig(
        enabled=enabled,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
    )


def _payload() -> IngestReviewPayload:
    return IngestReviewPayload(
        review_target="K.01 表3 check with 表1 漏读发现",
        review_type="missing_object_discovery",
        program_profile_hint=K01_PROFILE_HINT,
        coding_result={
            "classified_sheet": "K.01 Agree SL to GL",
            "recognized_sections": ["b1_bkd_main_table", "b2_movement_tb_reconciliation"],
            "missing_sections": ["b4_table3_check_with_table1"],
            "recognition_confidence": 0.58,
            "conflicts": ["duplicate_anchor:b4_table3_check_with_table1"],
        },
        expected_object={
            "procedure": "K.01",
            "object_type": "module",
            "object_name": "b4_table3_check_with_table1",
        },
        candidate_previews=[
            IngestReviewCandidatePreview(
                sheet_name="K.01 Agree SL to GL",
                name_score=0.9,
                content_score=0.7,
                preview_lines=[
                    {"row": 38, "text": "表2 固定资产清单分类汇总"},
                    {"row": 45, "text": "表2 check with 表1 差异 Notes"},
                    {"row": 82, "text": "表4 折旧费用与利润表科目核对 差异"},
                ],
                anchor_hits=[
                    {"row": 45, "anchors": ["表2 check with 表1", "差异"]},
                    {"row": 82, "anchors": ["表4", "折旧费用与利润表"]},
                ],
            )
        ],
        question="请判断 coding 是否可能漏识别 K.01 表3。",
    )


def test_ingest_review_prompt_sets_boundaries():
    assert "不是重新读取整本 Excel" in SYSTEM_PROMPT
    assert "不得直接给出金额勾稽结论" in SYSTEM_PROMPT
    assert "不得将低置信度读取直接改成高置信度" in SYSTEM_PROMPT
    assert "只提出候选 sheet" in SYSTEM_PROMPT
    assert "表3 check、TB check、表4折旧核对是不同专题" in K01_PROFILE_HINT


def test_build_user_prompt_includes_payload_and_k01_hint():
    prompt = build_ingest_review_user_prompt(_payload())
    assert "K.01 表3 check with 表1 漏读发现" in prompt
    assert "missing_object_discovery" in prompt
    assert "program_profile_hint" in prompt
    assert "表4折旧费用与利润表核对的差异不得被当作 TB 差异" in prompt


def test_run_ingest_review_disabled_returns_none():
    result, raw = run_ingest_review(_config(enabled=False), _payload())
    assert result is None
    assert raw is None


def test_parse_valid_suspicious_result():
    raw = {
        "assessment": "suspicious",
        "risk_level": "high",
        "risk_area": "missing_module",
        "suspected_object": "b4_table3_check_with_table1",
        "candidate_sheet": "K.01 Agree SL to GL",
        "candidate_rows": [45],
        "evidence_anchors": ["表2 check with 表1", "差异"],
        "rationale": "第45行出现表2 check with 表1。",
        "suggested_action": "二次读取第45行附近。",
        "should_retry_deterministic_ingest": True,
        "manual_review_focus": "核对第45行附近。",
    }
    result = parse_ingest_review_result(raw, _payload())
    assert result is not None
    assert result.assessment == "suspicious"
    assert result.candidate_rows == [45]
    assert result.should_retry_deterministic_ingest is True


def test_parse_rejects_unknown_candidate_sheet():
    raw = {
        "assessment": "suspicious",
        "risk_level": "high",
        "risk_area": "missing_module",
        "candidate_sheet": "Invented Sheet",
        "candidate_rows": [45],
        "evidence_anchors": ["表2 check with 表1"],
    }
    assert parse_ingest_review_result(raw, _payload()) is None


def test_parse_rejects_invented_candidate_row():
    raw = {
        "assessment": "suspicious",
        "risk_level": "high",
        "risk_area": "missing_module",
        "candidate_sheet": "K.01 Agree SL to GL",
        "candidate_rows": [999],
        "evidence_anchors": ["表2 check with 表1"],
    }
    assert parse_ingest_review_result(raw, _payload()) is None


def test_parse_rejects_invented_anchor():
    raw = {
        "assessment": "suspicious",
        "risk_level": "high",
        "risk_area": "missing_module",
        "candidate_sheet": "K.01 Agree SL to GL",
        "candidate_rows": [45],
        "evidence_anchors": ["不存在的锚点"],
    }
    assert parse_ingest_review_result(raw, _payload()) is None


def test_parse_rejects_invalid_assessment():
    raw = {
        "assessment": "pass",
        "risk_level": "low",
        "risk_area": "other",
    }
    assert parse_ingest_review_result(raw, _payload()) is None


def test_parse_rejects_severity_override():
    raw = {
        "assessment": "suspicious",
        "risk_level": "high",
        "risk_area": "missing_module",
        "candidate_sheet": "K.01 Agree SL to GL",
        "candidate_rows": [45],
        "evidence_anchors": ["表2 check with 表1"],
        "severity": "FAIL",
    }
    assert parse_ingest_review_result(raw, _payload()) is None


def test_run_ingest_review_returns_validated_result_and_raw():
    raw = {
        "assessment": "likely_ok",
        "risk_level": "low",
        "risk_area": "section_boundary",
        "candidate_sheet": "K.01 Agree SL to GL",
        "candidate_rows": [],
        "evidence_anchors": [],
        "rationale": "未见明显错分证据。",
        "should_retry_deterministic_ingest": False,
    }
    with patch("llm.ingest_review.chat_completion_json", return_value=raw):
        result, returned_raw = run_ingest_review(_config(), _payload())

    assert returned_raw == raw
    assert result is not None
    assert result.assessment == "likely_ok"


def test_build_missing_k01_payload_from_candidate_workbook(tmp_path: Path):
    path = tmp_path / "missing_k01_candidate.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K01 SL-GL"
    ws.append(["表1", "固定资产类别", "年初余额", "年末余额", "审定数"])
    ws.append(["TB-原值", "差异", "Notes"])
    wb.save(path)
    wb.close()

    payload = build_missing_k01_ingest_review_payload(
        workbook_path=str(path),
        workbook_sheet_titles=["K01 SL-GL"],
    )

    assert payload is not None
    assert payload.review_type == "missing_object_discovery"
    assert payload.expected_object["object_type"] == "sheet"
    assert payload.candidate_previews[0].sheet_name == "K01 SL-GL"
    assert payload.candidate_previews[0].anchor_hits


def test_run_workbook_ingest_reviews_handles_missing_k01(tmp_path: Path):
    path = tmp_path / "missing_k01_candidate.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K01 SL-GL"
    ws.append(["表1", "固定资产类别", "年初余额", "年末余额", "审定数"])
    ws.append(["表2 check with 表1", "差异", "Notes"])
    wb.save(path)
    wb.close()

    raw = {
        "assessment": "suspicious",
        "risk_level": "high",
        "risk_area": "missing_sheet",
        "suspected_object": "K.01 Agree SL to GL",
        "candidate_sheet": "K01 SL-GL",
        "candidate_rows": [1],
        "evidence_anchors": ["表1", "固定资产类别"],
        "rationale": "候选 sheet 出现 K.01 后推锚点。",
        "suggested_action": "对候选 sheet 执行 deterministic ingest。",
        "should_retry_deterministic_ingest": True,
        "manual_review_focus": "打开 K01 SL-GL 核对是否为 K.01。",
    }
    with patch("llm.ingest_review.chat_completion_json", return_value=raw):
        results = run_workbook_ingest_reviews(
            _config(),
            rollforward=None,
            workbook_path=str(path),
            workbook_sheet_titles=["K01 SL-GL"],
        )

    assert len(results) == 1
    assert results[0].assessment == "suspicious"
    assert results[0].risk_area == "missing_sheet"


def test_run_workbook_ingest_reviews_covers_all_core_program_sheets(tmp_path: Path):
    path = tmp_path / "all_program_candidates.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "汇总"
    for title in (
        "K.00 Lead Sheet",
        "K.01 Agree SL to GL",
        "FA list",
        "新增清单",
        "K.02.1 新增测试",
        "K.02.1a 新增选样输出",
        "处置清单",
        "K.02.2 处置测试",
        "K.02.2a 处置选样输出",
        "K.03.1 SAP",
        "K.03.2 折旧测试TOD",
        "K.03.3 折旧政策复核",
    ):
        wb.create_sheet(title)
    wb.save(path)
    wb.close()

    def fake_chat_completion_json(*args, **kwargs):
        user = kwargs["user"]
        payload = user.split("输入数据：", 1)[1].strip()
        data = __import__("json").loads(payload)
        candidate = data["candidate_previews"][0]
        return {
            "assessment": "suspicious",
            "risk_level": "medium",
            "risk_area": "missing_sheet",
            "suspected_object": data["expected_object"]["object_name"],
            "candidate_sheet": candidate["sheet_name"],
            "candidate_rows": [],
            "evidence_anchors": [],
            "rationale": "mock project-level missing sheet review",
            "suggested_action": "人工核对候选 sheet。",
            "should_retry_deterministic_ingest": False,
            "manual_review_focus": "确认 sheet 类型。",
        }

    with patch("llm.ingest_review.chat_completion_json", side_effect=fake_chat_completion_json):
        results = run_workbook_ingest_reviews(
            _config(),
            rollforward=None,
            workbook_path=str(path),
            workbook_sheet_titles=wb.sheetnames,
            recognized_sheet_kinds={},
        )

    assert len(results) == len(EXPECTED_INGEST_OBJECTS)
    assert {r.procedure_code for r in results} >= {"SUMMARY", "K.00", "K.01", "K.02.1", "K.02.2", "K.03.1", "K.03.2", "K.03.3"}
