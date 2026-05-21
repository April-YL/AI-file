from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """你是固定资产审计底稿的质检助手。
你会收到：
1) 规则引擎产出的 findings（severity 已确定）；
2) 整底稿结构化摘录 workbook_excerpt（汇总、K.00 Lead、K.01 后推、FA/新增/处置清单、跨表勾稽等，已脱敏）。

你必须遵守：
1. 不得修改、否定规则引擎已给出的 severity（FAIL/WARN/NEED_REVIEW/PASS）。
2. 不得编造摘录中未出现的数据或金额；不确定时写明“需人工打开底稿核对”。
3. 对 NEED_REVIEW 项给出简短复核建议；结合 workbook_excerpt 对 Lead 预期分析、波动说明、CRA/TT、后推与清单一致性提出关注点。
4. 对 FAIL/WARN 可在 executive_summary 中说明优先处理顺序。
5. 使用中文回复。
6. 仅输出一个 JSON 对象，不要 markdown 代码块。"""


def build_psp_context_block(summary_programs: list[dict[str, Any]]) -> str:
    if not summary_programs:
        return ""
    return (
        "\n\n汇总页程序表（已脱敏，供 AE-003 PSP/拒绝理由参考）：\n"
        f"{json.dumps(summary_programs, ensure_ascii=False, indent=2)}"
    )


def build_workbook_excerpt_block(workbook_excerpt: dict[str, Any] | None) -> str:
    if not workbook_excerpt:
        return ""
    return (
        "\n\n整底稿结构化摘录 workbook_excerpt（已脱敏，勿当作完整底稿）：\n"
        f"{json.dumps(workbook_excerpt, ensure_ascii=False, indent=2)}"
    )


def build_review_user_prompt(
    *,
    source_file: str,
    procedure_code: str,
    issues: list[dict[str, Any]],
    summary_programs: list[dict[str, Any]] | None = None,
    workbook_excerpt: dict[str, Any] | None = None,
) -> str:
    need_review = [i for i in issues if i.get("severity") == "NEED_REVIEW"]
    payload = {
        "source_file": source_file,
        "procedure_code": procedure_code,
        "issue_count": len(issues),
        "need_review_count": len(need_review),
        "issues": issues,
    }
    if workbook_excerpt:
        payload["workbook_excerpt"] = workbook_excerpt

    return (
        "请根据以下脱敏后的质检 findings 与整底稿摘录生成复核意见。\n\n"
        "输出 JSON 格式：\n"
        "{\n"
        '  "executive_summary": "整体结论与优先关注项（3-6句，可引用 Lead/后推/汇总要点）",\n'
        '  "need_review_notes": [\n'
        "    {\n"
        '      "rule_id": "与输入一致",\n'
        '      "dict_rule_code": "可选",\n'
        '      "llm_note": "复核关注点（可引用 workbook_excerpt 中的具体块）",\n'
        '      "suggested_action": "建议 preparer/reviewer 采取的动作"\n'
        "    }\n"
        "  ],\n"
        '  "lead_focus_notes": ["可选，针对 K.00 各模块的额外提示，字符串数组"]\n'
        "}\n\n"
        f"输入数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        + (
            ""
            if workbook_excerpt
            else build_psp_context_block(summary_programs or [])
        )
    )
