"""Build browsable HTML index for agent-transcripts JSONL files."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(r"E:\AI file\agent-transcripts")
OUT = Path(r"E:\AI file\docs\cursor-transcript-index.html")


def title_from_jsonl(path: Path) -> tuple[str, str]:
    first = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("role") != "user":
            continue
        content = row.get("message", {}).get("content", [])
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    first = block.get("text", "")
                    break
        break
    m = re.search(r"<user_query>\s*(.+?)(?:\n|$)", first, re.S)
    title = re.sub(r"\s+", " ", (m.group(1) if m else first).strip())[:100]
    title = re.sub(r"<[^>]+>", "", title)
    preview = re.sub(r"\s+", " ", first.strip())[:300]
    return title or path.parent.name[:8], preview


def main() -> None:
    items = []
    for jsonl in sorted(ROOT.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        title, preview = title_from_jsonl(jsonl)
        rel = jsonl.relative_to(Path(r"E:\AI file"))
        items.append(
            {
                "title": title,
                "preview": preview,
                "rel": rel.as_posix(),
                "mtime": jsonl.stat().st_mtime,
                "size_kb": round(jsonl.stat().st_size / 1024, 1),
            }
        )

    rows = []
    for it in items:
        rows.append(
            f"""<tr>
  <td>{html.escape(it['title'])}</td>
  <td>{it['size_kb']} KB</td>
  <td><code>{html.escape(it['rel'])}</code></td>
  <td>{html.escape(it['preview'])}</td>
</tr>"""
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Cursor Agent 历史对话索引</title>
<style>
body {{ font-family: Segoe UI, sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
th {{ background: #f5f5f5; }}
code {{ font-size: 12px; }}
</style></head><body>
<h1>Cursor Agent 历史对话索引（{len(items)} 条）</h1>
<p>JSONL 无法稳定恢复 Cursor 侧边栏时，可在 Cursor 中直接打开下方路径，或在新 Agent 会话中 @ 引用该文件。</p>
<table>
<tr><th>标题</th><th>大小</th><th>路径</th><th>预览</th></tr>
{''.join(rows)}
</table>
</body></html>""",
        encoding="utf-8",
    )
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
