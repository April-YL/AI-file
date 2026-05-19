from __future__ import annotations

import re
from typing import Any

# 脱敏：常见测试编号与类似资产编号模式
_ASSET_ID_PATTERN = re.compile(
    r"\b(FA-TEST-\d+|FA-\d{3,}|CARD-\d+)\b",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    if not text:
        return text
    return _ASSET_ID_PATTERN.sub("[ASSET_ID]", text)


def redact_issue_dict(issue: dict[str, Any]) -> dict[str, Any]:
    out = dict(issue)
    for key in ("asset_id", "message", "suggestion"):
        val = out.get(key)
        if isinstance(val, str):
            out[key] = redact_text(val)
    return out


def redact_issues_for_llm(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [redact_issue_dict(i) for i in issues]


def redact_program_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("procedure_name", "sheet_ref", "execution_status", "waiver_reason", "notes"):
        val = out.get(key)
        if isinstance(val, str):
            out[key] = redact_text(val)
    return out


def redact_programs_for_llm(programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [redact_program_row(p) for p in programs]
