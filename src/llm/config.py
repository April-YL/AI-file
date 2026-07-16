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
    identification_enabled: bool = False
    identification_min_confidence: float = 0.75
    rule_review_enabled: bool | None = None
    hybrid_rule_enabled: bool | None = None
    narrative_enabled: bool | None = None
    disabled_rule_ids: frozenset[str] = frozenset()

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


def _env_optional_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    normalized = raw.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise LlmConfigError(f"{name} must be a boolean.")


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
    identification_enabled = _env_bool("FA_QC_LLM_IDENTIFICATION_ENABLED", False)
    identification_min_confidence = _env_float(
        "FA_QC_LLM_IDENTIFICATION_MIN_CONFIDENCE", 0.75
    )
    rule_review_enabled = _env_optional_bool("FA_QC_LLM_RULE_REVIEW_ENABLED")
    hybrid_rule_enabled = _env_optional_bool("FA_QC_LLM_HYBRID_RULE_ENABLED")
    narrative_enabled = _env_optional_bool("FA_QC_LLM_NARRATIVE_ENABLED")
    disabled_rule_ids = frozenset(
        item.strip()
        for item in os.getenv("FA_QC_LLM_DISABLED_RULE_IDS", "").split(",")
        if item.strip()
    )

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
    if not 0 <= identification_min_confidence <= 1:
        raise LlmConfigError(
            "FA_QC_LLM_IDENTIFICATION_MIN_CONFIDENCE must be between 0 and 1."
        )

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
        identification_enabled=identification_enabled,
        identification_min_confidence=identification_min_confidence,
        rule_review_enabled=rule_review_enabled,
        hybrid_rule_enabled=hybrid_rule_enabled,
        narrative_enabled=narrative_enabled,
        disabled_rule_ids=disabled_rule_ids,
    )


def build_llm_config(
    *,
    enabled: bool,
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "",
    model: str = "gpt-4o-mini",
    timeout: float = 60.0,
    max_tokens: int = 4096,
    max_retries: int = 2,
    retry_backoff: float = 1.5,
    proxy: str | None = None,
    trust_env: bool = True,
    identification_enabled: bool = False,
    identification_min_confidence: float = 0.75,
    rule_review_enabled: bool | None = None,
    hybrid_rule_enabled: bool | None = None,
    narrative_enabled: bool | None = None,
    disabled_rule_ids: frozenset[str] | set[str] | tuple[str, ...] = frozenset(),
) -> LlmConfig:
    """Build LLM config from explicit UI/runtime inputs without reading .env."""
    base_url = (base_url or "").strip() or "https://api.openai.com/v1"
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    proxy = (proxy or "").strip() or None

    if enabled and not api_key:
        raise LlmConfigError("已启用大模型，但未填写 API Key。")
    if enabled and not model:
        raise LlmConfigError("已启用大模型，但未填写模型名称。")
    if timeout <= 0:
        raise LlmConfigError("超时时间必须大于 0。")
    if max_tokens <= 0:
        raise LlmConfigError("最大输出 token 必须大于 0。")
    if max_retries < 0:
        raise LlmConfigError("重试次数不能小于 0。")
    if retry_backoff < 0:
        raise LlmConfigError("重试等待时间不能小于 0。")
    if not 0 <= identification_min_confidence <= 1:
        raise LlmConfigError("字段识别最低置信度必须在 0 到 1 之间。")

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
        identification_enabled=identification_enabled,
        identification_min_confidence=identification_min_confidence,
        rule_review_enabled=rule_review_enabled,
        hybrid_rule_enabled=hybrid_rule_enabled,
        narrative_enabled=narrative_enabled,
        disabled_rule_ids=frozenset(disabled_rule_ids),
    )
