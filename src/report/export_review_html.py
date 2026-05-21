from __future__ import annotations

import html
from pathlib import Path

from report.procedure_labels import procedure_filter_options, procedure_label
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


def _lead_sheet_section_html(sec: dict | None) -> str:
    if not sec:
        return """
    <section class="card" id="lead-sheet-section">
      <h2>Lead（K.00）</h2>
      <p class="meta">未识别到 K.00 Lead 表或无此类数据。</p>
    </section>
        """

    lqc = sec.get("lead_qc") or {}
    sev = _esc(lqc.get("overall_severity"))
    ic = lqc.get("issue_count", 0)
    blocks = ", ".join(_esc(b) for b in (sec.get("blocks_detected") or []))
    layout = _esc(sec.get("layout_variant") or "标准 SWP")

    rule_rows = ""
    rules = lqc.get("rules") or {}
    sev_order = {"FAIL": 0, "WARN": 1, "NEED_REVIEW": 2, "PASS": 3}
    sorted_rules = sorted(
        rules.items(),
        key=lambda kv: (sev_order.get(kv[1].get("overall_severity"), 9), kv[0]),
    )
    for rule_id, rsec in sorted_rules:
        rule_rows += (
            f"<tr><td>{_esc(rsec.get('dict_rule_code'))}</td>"
            f"<td><code>{_esc(rule_id)}</code></td>"
            f"<td><strong>{_esc(rsec.get('overall_severity'))}</strong></td>"
            f"<td>{rsec.get('issue_count', 0)}</td></tr>\n"
        )

    detail_html = ""
    for rule_id, rsec in sorted_rules:
        osev = rsec.get("overall_severity")
        if osev not in ("FAIL", "WARN"):
            continue
        issues = rsec.get("issues") or []
        issue_rows = "".join(
            f"<tr><td>{_esc(i.get('severity'))}</td><td>{_esc(i.get('field'))}</td>"
            f"<td><code>{i.get('source_row')}</code></td>"
            f"<td>{_esc(i.get('message'))}</td>"
            f"<td>{_esc(i.get('suggestion'))}</td></tr>"
            for i in issues
        )
        detail_html += f"""
      <h4>{_esc(rsec.get('dict_rule_code'))} · <code>{_esc(rule_id)}</code> — {osev}</h4>
      <table>
        <thead><tr><th>级别</th><th>字段</th><th>行</th><th>说明</th><th>建议</th></tr></thead>
        <tbody>{issue_rows or '<tr><td colspan="5">无明细</td></tr>'}</tbody>
      </table>
        """

    notes = sec.get("ingest_notes") or []
    notes_html = "".join(f"<li>{_esc(n)}</li>" for n in notes) if notes else ""

    return f"""
    <section class="card" id="lead-sheet-section">
      <h2>Lead（K.00）</h2>
      <p class="meta">工作表：<strong>{_esc(sec.get('source_sheet'))}</strong>
        · 版式：<code>{layout}</code>
        · 识别块：{blocks or '—'}
        · CRA 行：{sec.get('cra_row_count', 0)}
        · 引导表行：{sec.get('movement_row_count', 0)}
        · 预期分析行：{len(sec.get('expectations') or [])}
      </p>
      <p>Lead 质检结论：<strong>{sev}</strong>（finding 数：{ic}）</p>
      <p class="meta">FAIL=明确不通过；WARN=建议确认；NEED_REVIEW=需与 Canvas/A3 人工比对；PASS=该项通过。</p>
      {'<h3>ingest 说明</h3><ul>' + notes_html + '</ul>' if notes_html else ''}
      <h3>规则矩阵</h3>
      <table>
        <thead><tr><th>字典码</th><th>rule_id</th><th>结论</th><th>finding 数</th></tr></thead>
        <tbody>{rule_rows or '<tr><td colspan="4">—</td></tr>'}</tbody>
      </table>
      {'<h3>需优先处理（FAIL / WARN）</h3>' + detail_html if detail_html else ''}
    </section>
    """


def _issues_section_html(report: QcReport) -> str:
    issues = report.issues
    if not issues:
        return """
  <section class="card" id="issues-section">
    <h2>问题清单（按程序）</h2>
    <p class="meta">无 findings。</p>
  </section>
        """

    codes = [i.procedure_code for i in issues]
    options = procedure_filter_options(codes)
    option_tags = "".join(
        f'<option value="{_esc(code)}">{_esc(label)}</option>' for code, label in options
    )
    rows = ""
    for issue in issues:
        d = issue.to_dict()
        proc = d.get("procedure_code") or ""
        rows += (
            f'<tr data-procedure="{_esc(proc)}">'
            f"<td>{_esc(procedure_label(proc))}</td>"
            f"<td><code>{_esc(proc)}</code></td>"
            f"<td>{_esc(d.get('dict_rule_code'))}</td>"
            f"<td><code>{_esc(d.get('rule_id'))}</code></td>"
            f"<td>{_esc(d.get('severity'))}</td>"
            f"<td>{_esc(d.get('source_sheet'))}</td>"
            f"<td><code>{d.get('source_row')}</code></td>"
            f"<td>{_esc(d.get('field'))}</td>"
            f"<td>{_esc(d.get('message'))}</td></tr>\n"
        )

    return f"""
  <section class="card" id="issues-section">
    <h2>问题清单（按程序）</h2>
    <p class="meta">
      <label for="proc-filter">筛选程序：</label>
      <select id="proc-filter" onchange="filterIssuesByProcedure()">{option_tags}</select>
      <span id="issues-count"></span>
    </p>
    <table id="issues-table">
      <thead><tr>
        <th>程序</th><th>代码</th><th>字典码</th><th>rule_id</th>
        <th>级别</th><th>工作表</th><th>行</th><th>字段</th><th>说明</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
    """


def _llm_enrichment_html(report: QcReport) -> str:
    le = report.llm_enrichment
    if le is None:
        return """
    <section class="card" id="llm-enrichment">
      <h2>大模型复核增强</h2>
      <p class="meta">未启用 --llm / UI 未勾选大模型增强。</p>
    </section>
        """
    if le.error:
        return f"""
    <section class="card" id="llm-enrichment">
      <h2>大模型复核增强</h2>
      <p class="meta">模型：<code>{_esc(le.model)}</code></p>
      <p style="color:#a33">调用失败：{_esc(le.error)}</p>
    </section>
        """
    notes_rows = "".join(
        f"<tr><td>{_esc(n.get('rule_id'))}</td><td>{_esc(n.get('dict_rule_code'))}</td>"
        f"<td>{_esc(n.get('llm_note'))}</td><td>{_esc(n.get('suggested_action'))}</td></tr>"
        for n in (le.need_review_notes or [])
    )
    lead_notes = "".join(f"<li>{_esc(x)}</li>" for x in (le.lead_focus_notes or []))
    sections = ", ".join(_esc(s) for s in (le.workbook_sections or []))
    return f"""
    <section class="card" id="llm-enrichment">
      <h2>大模型复核增强</h2>
      <p class="meta">模型：<code>{_esc(le.model)}</code>
        · 已纳入摘录：{sections or '—'}</p>
      <h3>执行摘要</h3>
      <p>{_esc(le.executive_summary)}</p>
      {'<h3>Lead 关注提示</h3><ul>' + lead_notes + '</ul>' if lead_notes else ''}
      <h3>NEED_REVIEW 复核建议</h3>
      <table>
        <thead><tr><th>rule_id</th><th>字典码</th><th>关注点</th><th>建议动作</th></tr></thead>
        <tbody>{notes_rows or '<tr><td colspan="4">无</td></tr>'}</tbody>
      </table>
    </section>
    """


def export_review_html(report: QcReport, path: str | Path) -> None:
    """生成便于浏览器打开的人工核对 HTML（与 JSON 报告配套）。"""
    path = Path(path)
    sections = report.manual_review_sections or []

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
    lead_html = _lead_sheet_section_html(report.lead_sheet_section)
    issues_html = _issues_section_html(report)
    llm_html = _llm_enrichment_html(report)

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
    tr[data-hidden="1"] {{ display: none; }}
  </style>
  <script>
    function filterIssuesByProcedure() {{
      var sel = document.getElementById('proc-filter');
      var v = sel ? sel.value : 'ALL';
      var rows = document.querySelectorAll('#issues-table tbody tr');
      var shown = 0;
      rows.forEach(function(tr) {{
        var show = v === 'ALL' || tr.getAttribute('data-procedure') === v;
        tr.setAttribute('data-hidden', show ? '0' : '1');
        if (show) shown++;
      }});
      var cnt = document.getElementById('issues-count');
      if (cnt) cnt.textContent = ' 显示 ' + shown + ' / ' + rows.length + ' 条';
    }}
    document.addEventListener('DOMContentLoaded', filterIssuesByProcedure);
  </script>
</head>
<body>
  <h1>固定资产质检报告 — 人工核对摘录</h1>
  <p>源文件：<code>{_esc(report.source_file)}</code></p>
  <div class="summary">
    <span class="badge">Overall: {_esc(report.summary.overall_severity.value)}</span>
    <span class="badge">Issues: {len(report.issues)}</span>
  </div>

  {summary_html}

  {lead_html}

  {issues_html}

  {llm_html}

  <h2>Checklist 摘录（与 Canvas 人工比对）</h2>
  {section_html or '<p>无 manual_review_sections 数据。</p>'}
</body>
</html>
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(html_doc)
