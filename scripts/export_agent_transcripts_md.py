"""Export agent-transcript JSONL files to readable Markdown under docs/history/."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_ROOT = ROOT / "agent-transcripts"
OUT_DIR = ROOT / "docs" / "history" / "sessions"
INDEX_PATH = ROOT / "docs" / "history" / "INDEX.md"
README_PATH = ROOT / "docs" / "history" / "README.md"
PATH_RE = re.compile(r"d:\\AI file", re.I)


def rewrite(text: str) -> str:
    return PATH_RE.sub(lambda _: r"E:\AI file", text)


def slugify(title: str, max_len: int = 40) -> str:
    s = re.sub(r"<[^>]+>", "", title)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:max_len] or "session").strip("-")


def title_from_user_text(text: str) -> str:
    m = re.search(r"<user_query>\s*(.+?)(?:\n|$)", text, re.S)
    raw = m.group(1) if m else text
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:100] or "未命名会话"


def parse_content(content) -> tuple[str, list[str]]:
    if isinstance(content, str):
        return rewrite(content), []
    if not isinstance(content, list):
        return rewrite(str(content)), []
    texts: list[str] = []
    tools: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            t = rewrite(str(block["text"]))
            t = re.sub(r"\[REDACTED\]", "_（模型推理过程已省略）_", t)
            texts.append(t)
        elif block.get("type") == "tool_use":
            name = block.get("name", "tool")
            inp = block.get("input") or {}
            if isinstance(inp, dict):
                brief = ", ".join(f"{k}={v!r}" for k, v in list(inp.items())[:3])
                if len(inp) > 3:
                    brief += ", ..."
            else:
                brief = str(inp)[:120]
            tools.append(f"`{name}`({brief})")
    return "\n\n".join(texts).strip(), tools


def export_session(jsonl: Path) -> dict:
    session_id = jsonl.parent.name
    mtime = datetime.fromtimestamp(jsonl.stat().st_mtime)
    date_str = mtime.strftime("%Y-%m-%d")
    rows = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    title = "未命名会话"
    for row in rows:
        if row.get("role") == "user":
            text, _ = parse_content(row.get("message", {}).get("content", []))
            if text:
                title = title_from_user_text(text)
                break

    slug = slugify(title)
    filename = f"{date_str}_{slug}_{session_id[:8]}.md"
    rel_src = jsonl.relative_to(ROOT).as_posix()

    parts = [
        f"# {title}",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        f"| 日期 | {date_str} |",
        f"| 会话 ID | `{session_id}` |",
        f"| 源文件 | `{rel_src}` |",
        f"| 消息条数 | {len(rows)} |",
        "",
        "> 由 `scripts/export_agent_transcripts_md.py` 从 JSONL 自动导出，便于阅读与检索。",
        "> 工具调用的**返回结果**未包含在 JSONL 中，完整结论请以 Git 代码与 `docs/handoff/latest.md` 为准。",
        "",
        "---",
        "",
    ]

    turn = 0
    for row in rows:
        role = row.get("role")
        if role not in {"user", "assistant"}:
            continue
        turn += 1
        text, tools = parse_content(row.get("message", {}).get("content", []))
        if not text and not tools:
            continue
        if role == "user":
            parts.append(f"## 用户 · 第 {turn} 轮")
        else:
            parts.append(f"## 助手 · 第 {turn} 轮")
        parts.append("")
        if text:
            parts.append(text)
            parts.append("")
        if tools:
            parts.append("<details>")
            parts.append(f"<summary>工具调用（{len(tools)} 次）</summary>")
            parts.append("")
            for t in tools:
                parts.append(f"- {t}")
            parts.append("")
            parts.append("</details>")
            parts.append("")

    out_path = OUT_DIR / filename
    out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

    return {
        "title": title,
        "date": date_str,
        "session_id": session_id,
        "filename": filename,
        "rel_md": out_path.relative_to(ROOT).as_posix(),
        "rel_src": rel_src,
        "size_kb": round(jsonl.stat().st_size / 1024, 1),
        "turns": len(rows),
        "mtime": mtime.timestamp(),
    }


def write_index(items: list[dict]) -> None:
    items = sorted(items, key=lambda x: x["mtime"], reverse=True)
    lines = [
        "# Agent 历史对话索引",
        "",
        "可读版 Markdown 会话存档，按时间倒序。",
        "",
        "重新导出：`python scripts/export_agent_transcripts_md.py`",
        "",
        "| 日期 | 标题 | 大小 | Markdown | 原始 JSONL |",
        "| --- | --- | --- | --- | --- |",
    ]
    for it in items:
        lines.append(
            f"| {it['date']} | {it['title']} | {it['size_kb']} KB | "
            f"[打开](sessions/{it['filename']}) | `{it['rel_src']}` |"
        )
    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme() -> None:
    README_PATH.write_text(
        """# Agent 历史对话存档

本目录存放从 `agent-transcripts/*.jsonl` 导出的**可读 Markdown**，方便随时查阅，不依赖 Cursor 侧边栏。

## 怎么用

1. 打开 [INDEX.md](INDEX.md) 按标题找会话
2. 进入 `sessions/` 下对应 `.md` 文件阅读
3. 在 Cursor 中 `@docs/history/sessions/xxx.md` 或 `@docs/history/INDEX.md` 让 Agent 引用

## 格式说明

每个 Markdown 文件包含：

- 会话元数据（日期、ID、源 JSONL 路径）
- 按轮次排列的**用户 / 助手**对话
- 助手轮次下的**工具调用**列表（折叠块）；工具**输出**不在 JSONL 中，故未导出

## 更新

新增或更新了 `agent-transcripts/` 下的 JSONL 后，在项目根目录执行：

```powershell
python scripts/export_agent_transcripts_md.py
```

## 与项目文档的关系

| 来源 | 用途 |
| --- | --- |
| `docs/history/sessions/*.md` | 回顾**讨论过程**、需求与决策背景 |
| `docs/handoff/latest.md` | **当前进度**与下一步（优先看这个） |
| Git 提交 / 代码 | **最终落地**的实现 |

## 隐私

导出文件可能含本地路径；请勿提交真实 API 密钥。提交前若需脱敏，可只保留 `docs/handoff/` 与代码，或将 `agent-transcripts/` 留在本机。
""",
        encoding="utf-8",
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for jsonl in sorted(TRANSCRIPT_ROOT.glob("*/*.jsonl")):
        items.append(export_session(jsonl))
        print(f"exported: {items[-1]['filename']}")
    write_index(items)
    write_readme()
    print(f"\nWrote {len(items)} sessions -> {OUT_DIR}")
    print(f"Index: {INDEX_PATH}")


if __name__ == "__main__":
    main()
