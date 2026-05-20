from __future__ import annotations

import html
from pathlib import Path

from report.summary import QcReport


def _esc(text: str | None) -> str:
    return html.escape(text or "—", quote=True)


def _summary_sheet_section_html(sec: dict | None) -> str:
    if not sec:
        return """
    <section class="card" id="summary-sheet-section">
      <h2>汇总页（PSP / AE-003）</h2>
      <p class="meta">未识别到汇总页或无此类数据（例如输入为仅 FA list 的 CSV）。</p>
    </section>
        """

    psp = sec.get("psp_completion") or {}
    sev = _esc(psp.get("overall_severity"))
    ic = psp.get("issue_count", 0)
    bindings = sec.get("column_bindings") or []
    bind_rows = "".join(
        f"<tr><td>{_esc(b.get('role'))}</td><td>{_esc(b.get('source_header'))}</td>"
        f"<td><code>{b.get('column_index')}</code></td></tr>"
        for b in bindings
    )
    notes = sec.get("ingest_notes") or []
    notes_html = "".join(f"<li>{_esc(n)}</li>" for n in notes) if notes else ""
    prog_rows = "".join(
        f"<tr><td>{_esc(p.get('procedure_name'))}</td>"
        f"<td>{_esc(p.get('sheet_ref'))}</td>"
        f"<td>{_esc(p.get('execution_status'))}</td>"
        f"<td>{_esc(p.get('waiver_reason'))}</td>"
        f"<td><code>{p.get('source_row')}</code></td></tr>"
        for p in (sec.get("programs") or [])
    )
    trunc = ""
    if sec.get("programs_truncated"):
        trunc = (
            f"<p class=\"meta\">程序表仅展示前 {sec.get('programs_in_report')} 行"
            f"（共 {sec.get('program_count')} 行）。</p>"
        )
    psp_issue_rows = "".join(
        f"<tr><td>{_esc(i.get('severity'))}</td><td>{_esc(i.get('field'))}</td>"
        f"<td>{_esc(i.get('message'))}</td></tr>"
        for i in (psp.get("issues") or [])
    )
    return f"""
    <section class="card" id="summary-sheet-section">
      <h2>汇总页（PSP / AE-003）</h2>
      <p class="meta">工作表：<strong>{_esc(sec.get('source_sheet'))}</strong>
        · 版式：<code>{_esc(sec.get('layout'))}</code>
        · 表头行：{_esc(str(sec.get("header_row")))}
        · 程序行数：{sec.get('program_count')}
      </p>
      <p>AE-003 结论：<strong>{sev}</strong>（finding 数：{ic}）</p>
      {trunc}
      <h3>列绑定</h3>
      <table>
        <thead><tr><th>角色</th><th>源表头</th><th>列(1-based)</th></tr></thead>
        <tbody>{bind_rows or '<tr><td colspan="3">—</td></tr>'}</tbody>
      </table>
      {'<h3>ingest 说明</h3><ul>' + notes_html + '</ul>' if notes_html else ''}
      <h3>程序表（解析结果）</h3>
      <table>
        <thead><tr><th>程序/说明</th><th>程序页</th><th>执行</th><th>不执行原因</th><th>行</th></tr></thead>
        <tbody>{prog_rows or '<tr><td colspan="5">—</td></tr>'}</tbody>
      </table>
      <h3>AE-003 Findings</h3>
      <table>
        <thead><tr><th>级别</th><th>字段</th><th>说明</th></tr></thead>
        <tbody>{psp_issue_rows or '<tr><td colspan="3">无（PASS）</td></tr>'}</tbody>
      </table>
    </section>
    """


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

    summary_html = _summary_sheet_section_html(report.summary_sheet_section)

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
  <div class="summary">
    <span class="badge">Overall: {_esc(report.summary.overall_severity.value)}</span>
    <span class="badge">Issues: {len(report.issues)}</span>
  </div>

  {summary_html}

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
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(html_doc)
