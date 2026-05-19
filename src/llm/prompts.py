from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """你是固定资产审计底稿的质检助手。
你只能根据提供的结构化 findings 做复核建议，不能访问完整底稿。
你必须遵守：
1. 不得修改、否定规则引擎已给出的 severity（FAIL/WARN/NEED_REVIEW）。
2. 不得编造底稿中未出现的事实。
3. 对 NEED_REVIEW 项给出简短复核建议；对其余项可在 executive_summary 中归纳。
4. 使用中文回复。
5. 仅输出一个 JSON 对象，不要 markdown 代码块。"""


def build_psp_context_block(summary_programs: list[dict[str, Any]]) -> str:
    if not summary_programs:
        return ""
    return (
        "\n\n汇总页程序表（已脱敏，供 AE-003 PSP/拒绝理由参考）：\n"
        f"{json.dumps(summary_programs, ensure_ascii=False, indent=2)}"
    )


def build_review_user_prompt(
    *,
    source_file: str,
    procedure_code: str,
    issues: list[dict[str, Any]],
    summary_programs: list[dict[str, Any]] | None = None,
) -> str:
    need_review = [i for i in issues if i.get("severity") == "NEED_REVIEW"]
    payload = {
        "source_file": source_file,
        "procedure_code": procedure_code,
        "issue_count": len(issues),
        "need_review_count": len(need_review),
        "issues": issues,
    }
    return (
        "请根据以下脱敏后的质检 findings 生成复核意见。\n\n"
        "输出 JSON 格式：\n"
        "{\n"
        '  "executive_summary": "整体结论与优先关注项（2-5句）",\n'
        '  "need_review_notes": [\n'
        "    {\n"
        '      "rule_id": "与输入一致",\n'
        '      "dict_rule_code": "可选",\n'
        '      "llm_note": "复核关注点",\n'
        '      "suggested_action": "建议 preparer/reviewer 采取的动作"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"输入数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        f"{build_psp_context_block(summary_programs or [])}"
    )
