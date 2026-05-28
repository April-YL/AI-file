from __future__ import annotations

from unittest.mock import patch

from ingest.lead_sheet import ExpectationRow, LeadMovementRow, LeadSheetDataset
from llm.config import LlmConfig
from llm.lead_review import build_lead_semantic_issues
from rules.models import Severity


def _config() -> LlmConfig:
    return LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
    )


def test_lead_expectation_semantic_warns_when_insufficient():
    lead = LeadSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.00 Lead Sheet",
        expectations=[
            ExpectationRow(
                account_change="固定资产新增",
                expectation="预计新增较上年增加。",
                source_row=30,
            )
        ],
    )
    with patch(
        "llm.lead_review.chat_completion_json",
        side_effect=[
            {
                "assessment": "insufficient",
                "rationale": "仅有方向描述，缺少阈值与证据来源。",
                "suggested_action": "补充TE/TT口径和支持性证据。",
            },
            {"assessment": "sufficient"},
        ],
    ):
        issues = build_lead_semantic_issues(lead, _config())

    assert any(
        i.rule_id == "lead_expectation_semantic"
        and i.severity == Severity.WARN
        and "语义上不足" in i.message
        for i in issues
    )


def test_lead_fluctuation_semantic_need_review_when_unclear():
    lead = LeadSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.00 Lead Sheet",
        fluctuation_notes="波动较大，已关注。",
        movement_rows=[
            LeadMovementRow(
                account_label="固定资产-机器设备",
                sheet_ref="K.00",
                values={"movement": "100000", "notes": ""},
                source_row=52,
            )
        ],
    )
    with patch(
        "llm.lead_review.chat_completion_json",
        return_value={
            "assessment": "unclear",
            "rationale": "未明确风险影响和后续程序。",
            "suggested_action": "补充风险结论与后续动作。",
        },
    ):
        issues = build_lead_semantic_issues(lead, _config())

    assert any(
        i.rule_id == "lead_fluctuation_notes_semantic"
        and i.severity == Severity.NEED_REVIEW
        and "语义不明确" in i.message
        for i in issues
    )


def test_lead_semantic_issues_skip_when_llm_returns_invalid():
    lead = LeadSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.00 Lead Sheet",
        expectations=[
            ExpectationRow(account_change="新增", expectation="预计稳定。", source_row=30)
        ],
        fluctuation_notes="本期波动合理。",
    )
    with patch(
        "llm.lead_review.chat_completion_json",
        side_effect=[{"assessment": "unknown"}, {"assessment": "unknown"}],
    ):
        issues = build_lead_semantic_issues(lead, _config())
    assert issues == []
