from unittest.mock import patch

from ingest.disposal_test_sheet import DisposalExecutionPathDataset, DisposalTestSheetDataset
from llm.config import LlmConfig
from llm.disposal_review import SYSTEM_PROMPT, build_disposal_llm_issues, build_disposal_review_payload
from rules.models import QcIssue, Severity


def _config(enabled: bool = True) -> LlmConfig:
    return LlmConfig(enabled=enabled, base_url="https://api.example.com/v1", api_key="sk-test", model="test")


def test_disposal_prompt_has_semantic_only_boundaries():
    assert "不重新计算金额" in SYSTEM_PROMPT
    assert "不得将 FAIL/WARN 改为 PASS" in SYSTEM_PROMPT
    assert "other_reduction_treatment" in SYSTEM_PROMPT


def test_payload_includes_deterministic_findings():
    payload = build_disposal_review_payload(
        disposal_test=DisposalTestSheetDataset(source_file="x", source_sheet="K.02.2"),
        prior_issues=[
            QcIssue(None, "rule-x", "field", Severity.FAIL, "差异", "处理", "K.02.2")
        ],
    )
    assert payload["review_policy"]["do_not_override_rule_findings"] is True
    assert payload["deterministic_rule_findings"][0]["rule_id"] == "rule-x"


def test_disabled_llm_returns_empty():
    assert build_disposal_llm_issues(_config(False)) == []


def test_insufficient_review_maps_to_warn():
    review = {
        "topics": [
            {
                "topic": "evidence_description",
                "assessment": "insufficient",
                "rationale": "未说明具体合同和审批单",
                "suggested_action": "补充证据索引",
            }
        ]
    }
    with patch("llm.disposal_review.chat_completion_json", return_value=review):
        issues = build_disposal_llm_issues(
            _config(),
            disposal_test=DisposalTestSheetDataset(source_file="x", source_sheet="K.02.2"),
            disposal_execution_path=DisposalExecutionPathDataset(
                path_kind="executed_package_complete",
                recognition_confidence=0.9,
                summary_source_row=8,
            ),
        )
    assert issues[0].severity == Severity.WARN
    assert issues[0].review_source == "LLM辅助判断"


def test_executed_disposal_skips_waiver_and_zero_other_reduction_topics():
    review = {
        "topics": [
            {"topic": "waiver_reason", "assessment": "insufficient"},
            {"topic": "other_reduction_treatment", "assessment": "insufficient"},
        ]
    }
    with patch("llm.disposal_review.chat_completion_json", return_value=review):
        issues = build_disposal_llm_issues(
            _config(),
            disposal_execution_path=DisposalExecutionPathDataset(
                path_kind="executed_package_complete",
                recognition_confidence=0.9,
            ),
        )
    assert issues == []
