import json

import httpx
import pytest

from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_chat_completion_json_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "executive_summary": "共 2 项需关注。",
                                "need_review_notes": [],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        return httpx.Response(200, json=payload)

    config = LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
        timeout=5.0,
    )
    client = httpx.Client(transport=_mock_transport(handler))
    result = chat_completion_json(config, system="sys", user="user", http_client=client)
    assert result["executive_summary"] == "共 2 项需关注。"


def test_chat_completion_json_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    config = LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="bad",
        model="m",
    )
    client = httpx.Client(transport=_mock_transport(handler))
    with pytest.raises(LlmClientError, match="401"):
        chat_completion_json(config, system="s", user="u", http_client=client)


def test_chat_completion_json_retries_temporary_http_error():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="temporary unavailable")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"ok": True})}},
                ]
            },
        )

    config = LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="m",
        max_retries=1,
        retry_backoff=0,
    )
    client = httpx.Client(transport=_mock_transport(handler))

    result = chat_completion_json(config, system="s", user="u", http_client=client)

    assert result == {"ok": True}
    assert calls == 2


def test_chat_completion_json_does_not_retry_auth_error():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, text="unauthorized")

    config = LlmConfig(
        enabled=True,
        base_url="https://api.example.com/v1",
        api_key="bad",
        model="m",
        max_retries=3,
        retry_backoff=0,
    )
    client = httpx.Client(transport=_mock_transport(handler))

    with pytest.raises(LlmClientError, match="401"):
        chat_completion_json(config, system="s", user="u", http_client=client)

    assert calls == 1
