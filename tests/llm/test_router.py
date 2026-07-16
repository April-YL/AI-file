import pytest

from llm.config import LlmConfig
from llm.router import LlmCapability, LlmCapabilityDisabled, LlmRouter


def _config(**overrides):
    values = {
        "enabled": True,
        "base_url": "https://api.example.com/v1",
        "api_key": "test-key",
        "model": "test-model",
    }
    values.update(overrides)
    return LlmConfig(**values)


def test_master_off_disables_all_capabilities():
    router = LlmRouter(_config(enabled=False))
    assert not router.is_enabled(LlmCapability.RULE_REVIEW)
    assert not router.is_enabled(LlmCapability.HYBRID_RULE)
    assert not router.is_enabled(LlmCapability.NARRATIVE)
    assert not router.is_enabled(LlmCapability.IDENTIFICATION)


def test_legacy_enabled_preserves_existing_capabilities_but_not_identification():
    router = LlmRouter(_config())
    assert router.is_enabled(LlmCapability.RULE_REVIEW)
    assert router.is_enabled(LlmCapability.HYBRID_RULE)
    assert router.is_enabled(LlmCapability.NARRATIVE)
    assert not router.is_enabled(LlmCapability.IDENTIFICATION)


def test_capability_and_rule_switches_are_combined():
    router = LlmRouter(_config(rule_review_enabled=False, disabled_rule_ids=frozenset({"rule-x"})))
    assert not router.is_enabled(LlmCapability.RULE_REVIEW)
    assert not router.is_enabled(LlmCapability.HYBRID_RULE, rule_id="rule-x")
    assert router.is_enabled(LlmCapability.HYBRID_RULE, rule_id="rule-y")


def test_disabled_call_is_traced_without_client_call(monkeypatch):
    monkeypatch.setattr("llm.router.chat_completion_json", lambda *args, **kwargs: pytest.fail("client must not be called"))
    router = LlmRouter(_config(identification_enabled=False))
    with pytest.raises(LlmCapabilityDisabled):
        router.complete_json(capability=LlmCapability.IDENTIFICATION, task="field_resolution", system="system", user="user")
    assert router.traces()[0]["status"] == "disabled"


def test_completed_call_has_safe_trace(monkeypatch):
    monkeypatch.setattr("llm.router.chat_completion_json", lambda *args, **kwargs: {"ok": True})
    router = LlmRouter(_config())
    result = router.complete_json(
        capability=LlmCapability.RULE_REVIEW,
        task="semantic",
        rule_id="rule-y",
        prompt_version="v1",
        system="secret system prompt",
        user="sensitive workbook excerpt",
    )
    assert result == {"ok": True}
    trace = router.traces()[0]
    assert trace["capability"] == "rule_review"
    assert trace["status"] == "completed"
    assert "secret" not in str(trace)
    assert "workbook" not in str(trace)
