"""K.01 Notes LLM 语义复核单测（不调用 API）。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from ingest.rollforward_sheet import RollforwardSheetDataset
from llm.config import LlmConfig
from llm.rollforward_notes_review import (
    RULE_ID,
    build_rollforward_notes_issues,
    build_rollforward_notes_review_payload,
    should_review_rollforward_notes,
)
from ingest.lead_sheet import LeadBasicInfoField, LeadSheetDataset, MaterialityCapture
from rules.models import QcIssue, Severity


def _config() -> LlmConfig:
    return LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
    )


def _lead_sad(sad: str = "50000") -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=[
            LeadBasicInfoField(
                field_key="sad",
                label="名义金额 (SAD)",
                value=sad,
                source_row=3,
                source_col=2,
            )
        ],
        materiality=[
            MaterialityCapture(
                field_key="sad",
                label="名义金额 (SAD)",
                workpaper_value=sad,
                source_row=3,
            )
        ],
    )


def _rollforward_tb_with_notes() -> RollforwardSheetDataset:
    return RollforwardSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.01 Agree SL to GL",
        header_row=1,
        mapped_fields=[],
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("100000")],
        tb_difference_row=40,
        tb_notes_text_present=True,
        tb_notes_row=42,
        tb_notes_text="差异为重分类影响，已与项目组确认，无需调整。",
        section_presence={"b2_movement_tb_reconciliation": True},
    )


def test_should_review_when_tb_material_diff_has_notes():
    lead = _lead_sad()
    rf = _rollforward_tb_with_notes()
    assert should_review_rollforward_notes(rf, lead=lead) is True


def test_should_not_review_when_no_material_diff():
    lead = _lead_sad()
    rf = RollforwardSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.01",
        header_row=1,
        mapped_fields=[],
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("100")],
        tb_notes_text_present=True,
        tb_notes_text="说明",
    )
    assert should_review_rollforward_notes(rf, lead=lead) is False


def test_payload_separates_topics():
    lead = _lead_sad()
    rf = _rollforward_tb_with_notes()
    payload = build_rollforward_notes_review_payload(rf, lead=lead)
    assert payload["notes_policy"]
    assert len(payload["review_topics"]) == 1
    assert payload["review_topics"][0]["topic_id"] == "tb_check"


def test_llm_insufficient_notes_warns():
    lead = _lead_sad()
    rf = _rollforward_tb_with_notes()
    mock_review = {
        "topics": [
            {
                "topic_id": "tb_check",
                "assessment": "insufficient",
                "rationale": "仅写差异小于 SAD，与摘录金额矛盾",
                "suggested_action": "补充调查过程与结论",
            }
        ]
    }
    with patch("llm.rollforward_notes_review.chat_completion_json", return_value=mock_review):
        issues = build_rollforward_notes_issues(rf, _config(), lead=lead)

    assert any(
        i.rule_id == RULE_ID
        and i.severity == Severity.WARN
        and "语义上不足" in i.message
        and i.review_source == "LLM辅助判断"
        for i in issues
    )


def test_llm_sufficient_no_issue():
    lead = _lead_sad()
    rf = _rollforward_tb_with_notes()
    mock_review = {
        "topics": [{"topic_id": "tb_check", "assessment": "sufficient", "rationale": ""}]
    }
    with patch("llm.rollforward_notes_review.chat_completion_json", return_value=mock_review):
        issues = build_rollforward_notes_issues(rf, _config(), lead=lead)
    assert issues == []


def test_table4_topic_triggered():
    lead = _lead_sad("50000")
    rf = RollforwardSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.01",
        header_row=1,
        mapped_fields=[],
        table4_difference=Decimal("80000"),
        table4_difference_row=85,
        table4_notes_text_present=True,
        table4_notes_text="分摊口径差异，已核对折旧政策。",
        section_presence={"b5_table4_depreciation_pl": True},
    )
    topics = build_rollforward_notes_review_payload(rf, lead=lead)["review_topics"]
    assert any(t["topic_id"] == "table4_depreciation" for t in topics)


def test_table4_topic_skipped_when_prior_deterministic_issue_exists():
    lead = _lead_sad("50000")
    rf = RollforwardSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.01",
        header_row=1,
        mapped_fields=[],
        table4_difference=Decimal("80000"),
        table4_difference_row=85,
        table4_notes_text_present=True,
        table4_notes_text="分摊口径差异，已核对折旧政策。",
        section_presence={"b5_table4_depreciation_pl": True},
    )
    prior = [
        QcIssue(
            asset_id=None,
            rule_id="rollforward_depreciation_pl_reconciliation",
            field="table4_notes_text",
            severity=Severity.NEED_REVIEW,
            message="existing deterministic issue",
            suggestion=None,
        )
    ]
    assert should_review_rollforward_notes(rf, lead=lead, prior_issues=prior) is False
