from __future__ import annotations

import html
from pathlib import Path

from report.summary import QcReport


def _esc(text: str | None) -> str:
    return html.escape(text or "—", quote=True)


def export_review_html(report: QcReport, path: str | Path) -> None:
    """生成便于浏览器打开的人工核对 HTML（与 JSON 报告配套）。"""
    path = Path(path)
    sections = report.manual_review_sections or []
    issues_rows = ""
    for issue in report.issues:
        d = issue.to_dict()
        issues_rows += (
            f"<tr><td>{_esc(d.get('dict_rule_code'))}</td>"
            f"<td>{_esc(d.get('severity'))}</td>"
            f"<td>{_esc(d.get('message'))}</td></tr>\n"
        )

    section_html = ""
    for sec in sections:
        sd = sec.to_dict() if hasattr(sec, "to_dict") else sec
        items = sd.get("items") or []
        if items and "field_key" in items[0]:
            rows = "".join(
                f"<tr><td>{_esc(it.get('label'))}</td>"
                f"<td>{_esc(it.get('workpaper_value'))}</td>"
                f"<td>{_esc(it.get('canvas_or_external_value'))}</td>"
                f"<td><code>{_esc(it.get('workpaper_cell'))}</code></td>"
                f"<td><code>{_esc(it.get('canvas_cell'))}</code></td></tr>"
                for it in items
            )
            table = (
                "<table><thead><tr><th>项目</th><th>底稿值</th>"
                "<th>Canvas/外部参考</th><th>底稿单元格</th><th>参考单元格</th>"
                f"</tr></thead><tbody>{rows}</tbody></table>"
            )
        elif items and "assertion" in items[0]:
            rows = "".join(
                f"<tr><td>{_esc(it.get('assertion'))}</td>"
                f"<td>{_esc(it.get('cra'))}</td>"
                f"<td>{_esc(it.get('tt'))}</td>"
                f"<td><code>{_esc(it.get('assertion_cell'))}</code></td></tr>"
                for it in items
            )
            table = (
                "<table><thead><tr><th>认定</th><th>CRA</th><th>TT</th>"
                f"<th>来源</th></tr></thead><tbody>{rows}</tbody></table>"
            )
        else:
            table = "<p><em>（无摘录数据，请人工打开 Lead 表核对）</em></p>"

        notes = "".join(f"<li>{_esc(n)}</li>" for n in (sd.get("notes") or []))
        section_html += f"""
        <section class="card" id="{_esc(sd.get('dict_rule_code'))}">
          <h2>{_esc(sd.get('checklist_prompt'))}</h2>
          <p class="meta">{_esc(sd.get('dict_rule_code'))} · {_esc(sd.get('source_sheet'))}</p>
          <p>{_esc(sd.get('instruction'))}</p>
          {table}
          {'<ul>' + notes + '</ul>' if notes else ''}
        </section>
        """

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>固定资产质检报告 — 人工核对</title>
  <style>
    body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 24px; background: #f6f7f9; }}
    h1 {{ font-size: 1.35rem; }}
    .card {{ background: #fff; border-radius: 8px; padding: 16px 20px; margin: 16px 0;
             box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 14px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; }}
    th {{ background: #eef1f6; }}
    .meta {{ color: #555; font-size: 13px; }}
    .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0; }}
    .badge {{ background: #eef; padding: 4px 10px; border-radius: 4px; }}
    code {{ font-size: 12px; }}
  </style>
</head>
<body>
  <h1>固定资产质检报告 — 人工核对摘录</h1>
  <p>源文件：<code>{_esc(report.source_file)}</code></p>
  <motion class="summary">
    <span class="badge">Overall: {_esc(report.summary.overall_severity.value)}</span>
    <span class="badge">Issues: {len(report.issues)}</span>
  </div>

  <h2>Checklist 摘录（与 Canvas 人工比对）</h2>
  {section_html or '<p>无 manual_review_sections 数据。</p>'}

  <section class="card">
    <h2>全部 Findings 摘要</h2>
    <table>
      <thead><tr><th>规则</th><th>级别</th><th>说明</th></tr></thead>
      <tbody>{issues_rows or '<tr><td colspan="3">无</td></tr>'}</tbody>
    </table>
  </section>
</body>
</html>
""".replace("<motion class=\"summary\">", '<div class="summary">')

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(html_doc)
