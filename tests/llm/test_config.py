import os

import pytest

from llm.config import LlmConfigError, load_llm_config


def test_load_llm_config_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FA_QC_LLM_ENABLED", raising=False)
    monkeypatch.delenv("FA_QC_LLM_API_KEY", raising=False)
    cfg = load_llm_config(cli_enabled=False)
    assert cfg.enabled is False


def test_load_llm_config_requires_api_key_when_enabled(monkeypatch):
    monkeypatch.setenv("FA_QC_LLM_API_KEY", "")
    with pytest.raises(LlmConfigError, match="FA_QC_LLM_API_KEY"):
        load_llm_config(cli_enabled=True)


def test_load_llm_config_from_env(monkeypatch):
    monkeypatch.setenv("FA_QC_LLM_ENABLED", "true")
    monkeypatch.setenv("FA_QC_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("FA_QC_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("FA_QC_LLM_MAX_RETRIES", "4")
    monkeypatch.setenv("FA_QC_LLM_RETRY_BACKOFF", "0.25")
    monkeypatch.setenv("FA_QC_LLM_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("FA_QC_LLM_TRUST_ENV", "false")
    cfg = load_llm_config()
    assert cfg.enabled is True
    assert cfg.api_key == "sk-test"
    assert "openai.com" in cfg.base_url
    assert cfg.max_retries == 4
    assert cfg.retry_backoff == 0.25
    assert cfg.proxy == "http://127.0.0.1:7890"
    assert cfg.trust_env is False


def test_load_llm_config_rejects_invalid_retry(monkeypatch):
    monkeypatch.setenv("FA_QC_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("FA_QC_LLM_MAX_RETRIES", "-1")
    with pytest.raises(LlmConfigError, match="FA_QC_LLM_MAX_RETRIES"):
        load_llm_config(cli_enabled=True)
