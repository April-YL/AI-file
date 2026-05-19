import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from ingest.records import load_fa_list_csv
from llm.config import LlmConfig
from llm.review import enrich_report_with_llm
from report.export_json import run_fa_list_qc

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_enrich_report_attaches_summary():
    report = run_fa_list_qc(load_fa_list_csv(FIXTURES / "fa_list_no_asset_id.csv"), llm=False)
    config = LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
    )

    mock_response = {
        "executive_summary": "建议人工确认资产编号列映射。",
        "need_review_notes": [
            {
                "rule_id": "unique_asset_id",
                "dict_rule_code": "FA-RC-002",
                "llm_note": "缺少编号列",
                "suggested_action": "核对表头同义词",
            }
        ],
    }

    with patch("llm.review.chat_completion_json", return_value=mock_response):
        enriched = enrich_report_with_llm(report, config)

    assert enriched.llm_enrichment is not None
    assert "编号" in enriched.llm_enrichment.executive_summary
    assert len(enriched.llm_enrichment.need_review_notes) == 1
    data = enriched.to_dict()
    assert "llm_enrichment" in data


def test_enrich_report_records_error_without_raising():
    report = run_fa_list_qc(load_fa_list_csv(FIXTURES / "fa_list_valid.csv"), llm=False)
    config = LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="m",
    )

    from llm.client import LlmClientError

    with patch(
        "llm.review.chat_completion_json",
        side_effect=LlmClientError("timeout"),
    ):
        enriched = enrich_report_with_llm(report, config)

    assert enriched.llm_enrichment is not None
    assert enriched.llm_enrichment.error == "timeout"
