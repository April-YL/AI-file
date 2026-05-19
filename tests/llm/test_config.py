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
    cfg = load_llm_config()
    assert cfg.enabled is True
    assert cfg.api_key == "sk-test"
    assert "openai.com" in cfg.base_url
