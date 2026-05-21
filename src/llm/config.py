from __future__ import annotations

import os
from dataclasses import dataclass


class LlmConfigError(ValueError):
    """LLM 配置无效或缺失。"""


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    max_tokens: int = 4096

    @property
    def chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_llm_config(*, cli_enabled: bool | None = None) -> LlmConfig:
    """
    从环境变量加载 LLM 配置。

    环境变量：
    - FA_QC_LLM_ENABLED
    - FA_QC_LLM_BASE_URL（默认 https://api.openai.com/v1）
    - FA_QC_LLM_API_KEY
    - FA_QC_LLM_MODEL（默认 gpt-4o-mini）
    - FA_QC_LLM_TIMEOUT（秒，默认 60）
    - FA_QC_LLM_MAX_TOKENS（默认 4096，整底稿摘录时建议 ≥4096）
    """
    enabled = _env_bool("FA_QC_LLM_ENABLED", False) if cli_enabled is None else cli_enabled
    base_url = os.getenv("FA_QC_LLM_BASE_URL", "https://api.openai.com/v1").strip()
    api_key = os.getenv("FA_QC_LLM_API_KEY", "").strip()
    model = os.getenv("FA_QC_LLM_MODEL", "gpt-4o-mini").strip()
    timeout = float(os.getenv("FA_QC_LLM_TIMEOUT", "60"))
    max_tokens = int(os.getenv("FA_QC_LLM_MAX_TOKENS", "4096"))

    if enabled and not api_key:
        raise LlmConfigError(
            "已启用大模型（--llm on 或 FA_QC_LLM_ENABLED=true），但未设置 FA_QC_LLM_API_KEY。"
        )
    if enabled and not model:
        raise LlmConfigError("FA_QC_LLM_MODEL 不能为空。")

    return LlmConfig(
        enabled=enabled,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        max_tokens=max_tokens,
    )
