#!/usr/bin/env python
"""测试 FA_QC_LLM_* 配置是否可连通（不跑整本底稿）。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfigError, load_llm_config
from llm.env_loader import load_project_dotenv
from llm.prompts import SYSTEM_PROMPT


def main() -> int:
    load_project_dotenv()
    try:
        config = load_llm_config(cli_enabled=True)
    except LlmConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        print(
            "请编辑项目根目录 .env：设置 FA_QC_LLM_API_KEY、"
            "FA_QC_LLM_BASE_URL、FA_QC_LLM_MODEL",
            file=sys.stderr,
        )
        return 1

    if not config.api_key or config.api_key.startswith("your-"):
        print(
            "FA_QC_LLM_API_KEY 仍为空或占位符，请在 .env 中填入真实密钥后重试。",
            file=sys.stderr,
        )
        return 1

    print(f"BASE_URL: {config.base_url}")
    print(f"MODEL:    {config.model}")
    print(f"URL:      {config.chat_completions_url}")
    print("正在发送探测请求…")

    try:
        data = chat_completion_json(
            config,
            system=SYSTEM_PROMPT,
            user='{"ping": true} 请仅返回 JSON：{"ok": true, "message": "pong"}',
        )
    except LlmClientError as e:
        print(f"调用失败: {e}", file=sys.stderr)
        return 2

    print("连通成功。模型返回片段:")
    print(str(data)[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
