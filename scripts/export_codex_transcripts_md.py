"""Export Codex rollout sessions to readable Markdown under docs/history/codex-sessions/."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_transcript import (
    DEFAULT_CODEX_HOME,
    DEFAULT_WORKSPACE,
    display_title,
    load_workspace_sessions,
    slugify,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "history" / "codex-sessions"
INDEX_PATH = ROOT / "docs" / "history" / "CODEX-INDEX.md"


def export_session(session) -> dict:
    title = display_title(session)
    date_str = datetime.fromtimestamp(session.updated_ms / 1000).strftime("%Y-%m-%d")
    slug = slugify(title)
    filename = f"{date_str}_{slug}_{session.thread_id[:8]}.md"
    source_paths = [path.as_posix() for path in session.source_files]

    parts = [
        f"# {title}",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        f"| 日期 | {date_str} |",
        f"| Codex 线程 ID | `{session.thread_id}` |",
        f"| 工作区 | `{session.cwd}` |",
        f"| 源文件数 | {len(source_paths)} |",
        f"| 对话轮次 | {len(session.turns)} |",
        "",
        "> 由 `scripts/export_codex_transcripts_md.py` 从 Codex `rollout-*.jsonl` 自动导出。",
        "> 中间过程（commentary）与工具输出已做精简；完整记录仍在 `~/.codex/sessions/`。",
        "",
        "**源文件**",
        "",
    ]
    for src in source_paths:
        parts.append(f"- `{src}`")
    parts.extend(["", "---", ""])

    turn_no = 0
    for turn in session.turns:
        turn_no += 1
        label = "用户" if turn.role == "user" else "Codex"
        parts.append(f"## {label} · 第 {turn_no} 轮")
        if turn.phase:
            parts.append(f"_（{turn.phase}）_")
        parts.append("")
        parts.append(turn.text)
        parts.append("")
        if turn.tools:
            parts.append("<details>")
            parts.append(f"<summary>工具调用（{len(turn.tools)} 次）</summary>")
            parts.append("")
            for tool in turn.tools:
                parts.append(f"- {tool}")
            parts.append("")
            parts.append("</details>")
            parts.append("")

    out_path = OUT_DIR / filename
    out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return {
        "title": title,
        "thread_name": session.title,
        "date": date_str,
        "thread_id": session.thread_id,
        "filename": filename,
        "rel_md": out_path.relative_to(ROOT).as_posix(),
        "size_kb": session.size_kb,
        "turns": len(session.turns),
        "updated_ms": session.updated_ms,
    }


def write_index(items: list[dict]) -> None:
    items = sorted(items, key=lambda x: x["updated_ms"], reverse=True)
    lines = [
        "# Codex 历史对话索引",
        "",
        "从本机 `~/.codex/sessions/` 导出的 **E:\\\\AI file** 工作区 Codex 会话。",
        "",
        "重新导出：",
        "",
        "```powershell",
        "python scripts/export_codex_transcripts_md.py",
        "```",
        "",
        "导入 Cursor 侧边栏（需先完全退出 Cursor）：",
        "",
        "```powershell",
        "python scripts/import_codex_transcripts_to_cursor.py",
        "```",
        "",
        "| 日期 | 标题 | 线程名 | 大小 | Markdown | Codex 线程 ID |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        lines.append(
            f"| {item['date']} | {item['title']} | {item['thread_name']} | "
            f"{item['size_kb']} KB | [打开](codex-sessions/{item['filename']}) | "
            f"`{item['thread_id']}` |"
        )
    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    sessions = load_workspace_sessions(
        codex_home=DEFAULT_CODEX_HOME,
        workspace=DEFAULT_WORKSPACE,
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for session in sessions:
        items.append(export_session(session))
        print(f"exported: {items[-1]['filename']}")
    write_index(items)
    print(f"\nWrote {len(items)} Codex sessions -> {OUT_DIR}")
    print(f"Index: {INDEX_PATH}")


if __name__ == "__main__":
    main()
