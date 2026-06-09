from __future__ import annotations

from unittest.mock import patch

from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionParameterItem,
    AdditionSampleOutputDataset,
    AdditionSampleRow,
    AdditionTestedSampleRow,
    AdditionTestSheetDataset,
)
from llm.addition_review import (
    RULE_ID,
    SYSTEM_PROMPT,
    build_addition_review_payload,
    run_addition_llm_review,
)
from llm.config import LlmConfig
from rules.models import QcIssue, Severity


def _config(*, enabled: bool = True) -> LlmConfig:
    return LlmConfig(
        enabled=enabled,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
    )


def _addition_test() -> AdditionTestSheetDataset:
    return AdditionTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.1 addition test",
        waiver_note_text="Additions below SAD; no TOD performed.",
        waiver_note_rows=[12],
        tested_samples=[
            AdditionTestedSampleRow(
                source_row=31,
                asset_id="FA-TEST-001",
                asset_name="Machine",
                original_value="1000",
                evidence_description="invoice and acceptance report",
                attribute_results=["ok", "ok"],
            )
        ],
        recognition_confidence=0.9,
    )


def _sample_output() -> AdditionSampleOutputDataset:
    return AdditionSampleOutputDataset(
        source_file="test.xlsx",
        source_sheet="K.02.1a addition sampling output",
        parameters={
            "te": AdditionParameterItem(label="TE", value="200", source_row=5),
            "cra": AdditionParameterItem(label="CRA", value="Low", source_row=6),
        },
        selected_samples=[
            AdditionSampleRow(
                source_row=40,
                asset_id="FA-TEST-001",
                asset_name="Machine",
                original_value="1000",
                sample_type="key item",
            )
        ],
        recognition_confidence=0.9,
    )


def test_addition_prompt_sets_semantic_only_boundaries():
    prompt = SYSTEM_PROMPT
    assert "You review only semantic sufficiency" in prompt
    assert "Do not calculate or conclude whether amounts agree" in prompt
    assert "Do not change or override any FAIL/WARN/NEED_REVIEW from rules" in prompt
    assert "sample_selection" in prompt
    assert "special_addition_source" in prompt


def test_build_addition_review_payload_includes_rule_findings_and_policy():
    prior = [
        QcIssue(
            asset_id=None,
            rule_id="addition_sample_pool_amount",
            field="sample_pool_amount",
            severity=Severity.WARN,
            message="sample pool mismatch",
            suggestion="review",
            procedure_code="K.02.1a",
        )
    ]
    payload = build_addition_review_payload(
        addition_test=_addition_test(),
        addition_sample_output=_sample_output(),
        addition_execution_path=AdditionExecutionPathDataset(
            path_kind="executed_package_complete",
            recognition_confidence=0.9,
            summary_source_row=8,
        ),
        prior_issues=prior,
    )

    assert payload["review_policy"]["do_not_override_rule_findings"] is True
    assert payload["addition_test"]["tested_sample_count"] == 1
    assert payload["addition_sample_output"]["selected_sample_count"] == 1
    assert payload["deterministic_rule_findings"][0]["rule_id"] == "addition_sample_pool_amount"


def test_run_addition_review_disabled_returns_empty():
    issues, review = run_addition_llm_review(
        _config(enabled=False),
        addition_test=_addition_test(),
        addition_sample_output=_sample_output(),
    )
    assert issues == []
    assert review is None


def test_run_addition_review_maps_insufficient_to_warn():
    mock_review = {
        "topics": [
            {
                "topic": "sample_selection",
                "assessment": "insufficient",
                "rationale": "samples listed but no selection basis",
                "missing_evidence": ["selection rationale"],
                "suggested_action": "document key-item or sampling rationale",
            }
        ]
    }
    with patch("llm.addition_review.chat_completion_json", return_value=mock_review):
        issues, review = run_addition_llm_review(
            _config(),
            addition_test=_addition_test(),
            addition_sample_output=_sample_output(),
        )

    assert review == mock_review
    assert len(issues) == 1
    assert issues[0].rule_id == RULE_ID
    assert issues[0].severity == Severity.WARN
    assert issues[0].field == "sample_selection"
    assert issues[0].procedure_code == "K.02.1"


def test_run_addition_review_maps_unclear_to_need_review():
    mock_review = {
        "topics": [
            {
                "topic": "cross_sheet_explanation",
                "assessment": "unclear",
                "rationale": "cannot tell whether narrative explains rule finding",
                "missing_evidence": [],
                "suggested_action": "",
            }
        ]
    }
    with patch("llm.addition_review.chat_completion_json", return_value=mock_review):
        issues, _ = run_addition_llm_review(
            _config(),
            addition_test=_addition_test(),
            addition_sample_output=_sample_output(),
        )

    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].field == "cross_sheet_explanation"
