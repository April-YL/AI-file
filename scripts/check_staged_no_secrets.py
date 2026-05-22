#!/usr/bin/env python
"""提交前检查：暂存区不得包含 .env 或明文 API 密钥。"""

from __future__ import annotations

import re
import subprocess
import sys

# 仅 .env.example 允许入库
_FORBIDDEN_PATHS = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
}

_SECRET_PATTERNS = (
    re.compile(r"FA_QC_LLM_API_KEY\s*=\s*['\"]?sk-", re.I),
    re.compile(r"Bearer\s+sk-", re.I),
    re.compile(r"OPENAI_API_KEY\s*=\s*['\"]?sk-", re.I),
)


def _git(*args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0 and args[0] != "diff":
        return ""
    return r.stdout or ""


def main() -> int:
    staged = _git("diff", "--cached", "--name-only").splitlines()
    errors: list[str] = []

    for path in staged:
        norm = path.replace("\\", "/").strip()
        base = norm.split("/")[-1]
        if base in _FORBIDDEN_PATHS or (
            base.startswith(".env") and base != ".env.example"
        ):
            errors.append(f"禁止暂存密钥文件: {path}")

    diff = _git("diff", "--cached")
    added_only = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    for pat in _SECRET_PATTERNS:
        if pat.search(added_only):
            errors.append(
                f"暂存区 diff 疑似含 API 密钥（匹配 {pat.pattern}），请从暂存区移除"
            )
            break

    if errors:
        print("密钥安全检查失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\n处理: git restore --staged .env ；密钥只放在本地 .env（已在 .gitignore）。\n"
            "详见 docs/data-security.md",
            file=sys.stderr,
        )
        return 1

    print("密钥安全检查通过（暂存区无 .env / 无明文 sk- 密钥）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
