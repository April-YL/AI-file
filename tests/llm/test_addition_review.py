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
from ingest.models import AssetRecord
from ingest.records import FaListDataset
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


def _sample_output_with_replacement() -> AdditionSampleOutputDataset:
    return AdditionSampleOutputDataset(
        source_file="test.xlsx",
        source_sheet="K.02.1a addition sampling output",
        selected_samples=[
            AdditionSampleRow(
                source_row=40,
                asset_id="FA-TEST-001",
                asset_name="Machine",
                original_value="1000",
                sample_type="代表性样本",
            ),
            AdditionSampleRow(
                source_row=41,
                asset_id="FA-TEST-R01",
                asset_name="Replacement machine",
                original_value="800",
                sample_type="替换样本",
            ),
        ],
        recognition_confidence=0.9,
    )


def test_addition_prompt_sets_semantic_only_boundaries():
    prompt = SYSTEM_PROMPT
    assert "你只复核文字说明是否充分" in prompt
    assert "不计算、不判断金额是否相符" in prompt
    assert "不要自行补事实" in prompt
    assert "sample_selection" in prompt
    assert "special_addition_source" in prompt
    assert "替换样本" in prompt
    assert "替代样本" in prompt
    assert "备选样本" in prompt
    assert "未明确启用" in prompt
    assert "不属于必须进入 K.02.1" in prompt


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


def test_addition_review_payload_separates_required_and_replacement_samples():
    payload = build_addition_review_payload(
        addition_test=_addition_test(),
        addition_sample_output=_sample_output_with_replacement(),
    )

    sample_output = payload["addition_sample_output"]
    assert sample_output["selected_sample_count"] == 2
    assert sample_output["required_test_sample_count"] == 1
    assert sample_output["required_test_samples"][0]["sample_type"] == "代表性样本"
    assert sample_output["optional_replacement_sample_count"] == 1
    assert sample_output["optional_replacement_samples"][0]["sample_type"] == "替换样本"
    assert "未明确启用" in sample_output["replacement_sample_policy"]


def test_run_addition_review_disabled_returns_empty():
    issues, review = run_addition_llm_review(
        _config(enabled=False),
        addition_test=_addition_test(),
        addition_sample_output=_sample_output(),
    )
    assert issues == []
    assert review is None


def test_run_addition_review_skips_sample_selection_findings():
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
    assert issues == []


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


def test_addition_review_skips_cip_transfer_special_source_by_default():
    mock_review = {
        "topics": [
            {
                "topic": "special_addition_source",
                "assessment": "insufficient",
                "rationale": "在建工程转入未说明测试安排",
                "missing_evidence": [],
                "suggested_action": "补充说明",
            }
        ]
    }
    addition_list = FaListDataset(
        source_file="case.xlsx",
        source_sheet="新增清单",
        mapped_fields=[],
        records=[
            AssetRecord(addition_method="购置"),
            AssetRecord(addition_method="在建工程转入"),
        ],
    )
    with patch("llm.addition_review.chat_completion_json", return_value=mock_review):
        issues, _ = run_addition_llm_review(_config(), addition_list=addition_list)

    assert issues == []
