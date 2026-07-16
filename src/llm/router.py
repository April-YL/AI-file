from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Any, Callable

from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig


class LlmCapability(str, Enum):
    IDENTIFICATION = "identification"
    RULE_REVIEW = "rule_review"
    HYBRID_RULE = "hybrid_rule"
    NARRATIVE = "narrative"


class LlmCapabilityDisabled(LlmClientError):
    """Requested LLM capability is disabled by the shared runtime policy."""


@dataclass(frozen=True)
class LlmCallTrace:
    capability: str
    task: str
    rule_id: str | None
    status: str
    seconds: float
    prompt_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "task": self.task,
            "rule_id": self.rule_id,
            "status": self.status,
            "seconds": round(self.seconds, 3),
            "prompt_version": self.prompt_version,
        }


class LlmRouter:
    """The only gateway from business modules to the LLM client."""

    def __init__(self, config: LlmConfig):
        self.config = config
        self._traces: list[LlmCallTrace] = []

    def is_enabled(
        self,
        capability: LlmCapability | str,
        *,
        rule_id: str | None = None,
    ) -> bool:
        if not self.config.enabled:
            return False
        if rule_id and rule_id in getattr(self.config, "disabled_rule_ids", frozenset()):
            return False
        capability = LlmCapability(capability)
        if capability == LlmCapability.IDENTIFICATION:
            return bool(getattr(self.config, "identification_enabled", False))
        setting = {
            LlmCapability.RULE_REVIEW: getattr(self.config, "rule_review_enabled", None),
            LlmCapability.HYBRID_RULE: getattr(self.config, "hybrid_rule_enabled", None),
            LlmCapability.NARRATIVE: getattr(self.config, "narrative_enabled", None),
        }[capability]
        return True if setting is None else bool(setting)

    def complete_json(
        self,
        *,
        capability: LlmCapability | str,
        task: str,
        system: str,
        user: str,
        rule_id: str | None = None,
        prompt_version: str | None = None,
        client: Callable[..., dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        capability = LlmCapability(capability)
        if not self.is_enabled(capability, rule_id=rule_id):
            self._record(capability, task, rule_id, "disabled", 0.0, prompt_version)
            raise LlmCapabilityDisabled(
                f"LLM capability {capability.value!r} is disabled for {rule_id or task!r}."
            )
        started = perf_counter()
        try:
            completion_client = client or chat_completion_json
            result = completion_client(self.config, system=system, user=user)
        except Exception:
            self._record(capability, task, rule_id, "failed", perf_counter() - started, prompt_version)
            raise
        self._record(capability, task, rule_id, "completed", perf_counter() - started, prompt_version)
        return result

    def traces(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._traces]

    def _record(
        self,
        capability: LlmCapability,
        task: str,
        rule_id: str | None,
        status: str,
        seconds: float,
        prompt_version: str | None,
    ) -> None:
        self._traces.append(
            LlmCallTrace(
                capability=capability.value,
                task=task,
                rule_id=rule_id,
                status=status,
                seconds=max(seconds, 0.0),
                prompt_version=prompt_version,
            )
        )
