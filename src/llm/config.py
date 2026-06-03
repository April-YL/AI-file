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
    max_retries: int = 2
    retry_backoff: float = 1.5
    proxy: str | None = None
    trust_env: bool = True

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


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise LlmConfigError(f"{name} must be a number.") from e


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise LlmConfigError(f"{name} must be an integer.") from e


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
    - FA_QC_LLM_MAX_RETRIES（临时网络错误重试次数，默认 2）
    - FA_QC_LLM_RETRY_BACKOFF（重试等待秒数基数，默认 1.5）
    - FA_QC_LLM_PROXY（可选，代理地址）
    - FA_QC_LLM_TRUST_ENV（是否读取系统 HTTP(S)_PROXY，默认 true）
    """
    enabled = _env_bool("FA_QC_LLM_ENABLED", False) if cli_enabled is None else cli_enabled
    base_url = os.getenv("FA_QC_LLM_BASE_URL", "https://api.openai.com/v1").strip()
    api_key = os.getenv("FA_QC_LLM_API_KEY", "").strip()
    model = os.getenv("FA_QC_LLM_MODEL", "gpt-4o-mini").strip()
    timeout = _env_float("FA_QC_LLM_TIMEOUT", 60.0)
    max_tokens = _env_int("FA_QC_LLM_MAX_TOKENS", 4096)
    max_retries = _env_int("FA_QC_LLM_MAX_RETRIES", 2)
    retry_backoff = _env_float("FA_QC_LLM_RETRY_BACKOFF", 1.5)
    proxy = os.getenv("FA_QC_LLM_PROXY", "").strip() or None
    trust_env = _env_bool("FA_QC_LLM_TRUST_ENV", True)

    if enabled and not api_key:
        raise LlmConfigError(
            "已启用大模型（--llm on 或 FA_QC_LLM_ENABLED=true），但未设置 FA_QC_LLM_API_KEY。"
        )
    if enabled and not model:
        raise LlmConfigError("FA_QC_LLM_MODEL 不能为空。")
    if timeout <= 0:
        raise LlmConfigError("FA_QC_LLM_TIMEOUT must be greater than 0.")
    if max_tokens <= 0:
        raise LlmConfigError("FA_QC_LLM_MAX_TOKENS must be greater than 0.")
    if max_retries < 0:
        raise LlmConfigError("FA_QC_LLM_MAX_RETRIES must be 0 or greater.")
    if retry_backoff < 0:
        raise LlmConfigError("FA_QC_LLM_RETRY_BACKOFF must be 0 or greater.")

    return LlmConfig(
        enabled=enabled,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        max_tokens=max_tokens,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
        proxy=proxy,
        trust_env=trust_env,
    )
