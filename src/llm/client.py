from __future__ import annotations

import json
import time
from typing import Any

import httpx

from llm.config import LlmConfig


class LlmClientError(RuntimeError):
    """调用大模型 API 失败。"""


_RETRY_STATUS_CODES = {429, 502, 503, 504}


def chat_completion_json(
    config: LlmConfig,
    *,
    system: str,
    user: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """调用 OpenAI 兼容 chat/completions，解析返回 JSON 对象。"""
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": config.max_tokens,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    def _post(client: httpx.Client) -> httpx.Response:
        return client.post(config.chat_completions_url, headers=headers, json=body)

    try:
        if http_client is not None:
            resp = _post_with_retries(_post, http_client, config=config)
        else:
            with httpx.Client(
                timeout=config.timeout,
                proxy=config.proxy,
                trust_env=config.trust_env,
            ) as client:
                resp = _post_with_retries(_post, client, config=config)
    except httpx.TransportError as e:
        raise LlmClientError(
            f"无法连接 LLM API（已尝试 {config.max_retries + 1} 次）: {e}"
        ) from e

    if resp.status_code >= 400:
        raise LlmClientError(
            f"LLM API 返回 {resp.status_code}: {resp.text[:500]}"
        )

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise LlmClientError(f"LLM 响应格式异常: {resp.text[:500]}") from e

    return _parse_json_content(content)


def _post_with_retries(
    post_func,
    client: httpx.Client,
    *,
    config: LlmConfig,
) -> httpx.Response:
    attempts = config.max_retries + 1
    last_error: httpx.TransportError | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = post_func(client)
        except httpx.TransportError as e:
            last_error = e
            if attempt >= attempts:
                raise
            _sleep_before_retry(config.retry_backoff, attempt)
            continue

        if resp.status_code not in _RETRY_STATUS_CODES or attempt >= attempts:
            return resp
        _sleep_before_retry(config.retry_backoff, attempt)

    if last_error is not None:
        raise last_error
    raise LlmClientError("LLM API request failed without a response.")


def _sleep_before_retry(backoff: float, attempt: int) -> None:
    if backoff <= 0:
        return
    time.sleep(backoff * attempt)


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise LlmClientError(f"LLM 未返回合法 JSON: {text[:300]}") from e
    if not isinstance(parsed, dict):
        raise LlmClientError("LLM JSON 根节点必须是对象")
    return parsed
