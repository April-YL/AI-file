from __future__ import annotations

import json
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
        and i.review_source == "LLM辅助判断"
        and i.llm_review_type == "Lead预期分析充分性"
        and "语义上不足" in i.message
        for i in issues
    )


def test_lead_expectation_prompt_uses_rollforward_direction_criteria():
    lead = LeadSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.00 Lead Sheet",
        expectations=[
            ExpectationRow(
                account_change="固定资产新增",
                expectation="预计因新增产线购置设备，原值较上年增加。",
                source_row=30,
            )
        ],
        movement_rows=[
            LeadMovementRow(
                account_label="固定资产原值",
                sheet_ref="K.00",
                values={"movement": "500000", "movement_pct": "12%", "notes": "1"},
                source_row=52,
            )
        ],
    )
    with patch(
        "llm.lead_review.chat_completion_json",
        side_effect=[{"assessment": "sufficient"}, {"assessment": "sufficient"}],
    ) as mock_call:
        issues = build_lead_semantic_issues(lead, _config())

    assert issues == []
    system = mock_call.call_args_list[0].kwargs["system"]
    user = mock_call.call_args_list[0].kwargs["user"]
    payload = json.loads(user.split("输入：", 1)[1])
    assert "变动方向与 K.01 后推明细表" in system
    assert "购置及在建工程转入金额为 0" in system
    assert "折旧方法、使用寿命" in system
    assert "不要因为没有使用标准审计术语而判不足" in system
    assert payload["movement_rows"][0]["movement"] == "500000"
    assert "证据不足时返回 unclear" in payload["review_hint"]


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
        and i.review_source == "LLM辅助判断"
        and i.llm_review_type == "Lead异常波动说明充分性"
        and "语义不明确" in i.message
        for i in issues
    )


def test_lead_fluctuation_prompt_uses_note_threshold_and_unit_criteria():
    lead = LeadSheetDataset(
        source_file="wb.xlsx",
        source_sheet="K.00 Lead Sheet",
        fluctuation_notes="机器设备增加 500k，系新产线购置，已检查新增清单和合同。",
        movement_rows=[
            LeadMovementRow(
                account_label="固定资产-机器设备",
                sheet_ref="K.00",
                values={"movement": "500000", "movement_pct": "15%", "notes": "1"},
                source_row=52,
            )
        ],
    )
    with patch(
        "llm.lead_review.chat_completion_json",
        return_value={"assessment": "sufficient"},
    ) as mock_call:
        issues = build_lead_semantic_issues(lead, _config())

    assert issues == []
    system = mock_call.call_args_list[-1].kwargs["system"]
    user = mock_call.call_args_list[-1].kwargs["user"]
    payload = json.loads(user.split("输入：", 1)[1])
    assert "Note 编号" in system
    assert "k=千，m=百万" in system
    assert "无金额变动超过 TT" in system
    assert "只描述变动金额和变动幅度" in system
    assert "不得编造" in system
    assert payload["movement_rows"][0]["notes"] == "1"
    assert "单位换算" in payload["review_hint"]


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
