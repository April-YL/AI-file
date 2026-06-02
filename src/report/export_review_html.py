from __future__ import annotations

import html
from pathlib import Path

from report.export_annotated_workbook import COMMENTS_SHEET_NAME, comments_summary_stats
from report.procedure_labels import procedure_label
from report.summary import QcReport
from rules.models import Severity


def _esc(text: str | None) -> str:
    return html.escape(text or "—", quote=True)


def _severity_class(sev: str) -> str:
    return {
        "FAIL": "sev-fail",
        "WARN": "sev-warn",
        "NEED_REVIEW": "sev-nr",
        "PASS": "sev-pass",
    }.get(sev, "")


def _findings_only_html(report: QcReport) -> str:
    """精简 HTML：仅展示 findings 清单与汇总统计。"""
    issues = [i for i in report.issues if i.severity != Severity.PASS]
    stats = comments_summary_stats(report)
    sev_order = {"FAIL": 0, "WARN": 1, "NEED_REVIEW": 2}
    issues = sorted(
        issues,
        key=lambda i: (
            sev_order.get(i.severity.value, 9),
            i.source_sheet or "",
            i.source_row or 0,
        ),
    )

    rows = ""
    for idx, issue in enumerate(issues, start=1):
        d = issue.to_dict()
        cell = ""
        if issue.source_row:
            from openpyxl.utils import get_column_letter

            cell = f"${get_column_letter(2)}${issue.source_row}"
        rows += (
            f'<tr class="{_severity_class(issue.severity.value)}">'
            f"<td>{idx}</td>"
            f'<td><strong>{_esc(issue.severity.value)}</strong></td>'
            f"<td>{_esc(d.get('review_source'))}</td>"
            f"<td>{_esc(procedure_label(d.get('procedure_code')))}</td>"
            f"<td>{_esc(d.get('source_sheet'))}</td>"
            f"<td><code>{_esc(cell) if cell else '—'}</code></td>"
            f"<td>{_esc(d.get('dict_rule_code'))}</td>"
            f"<td>{_esc(d.get('message'))}</td></tr>\n"
        )

    return f"""
  <section class="card" id="findings">
    <h2>Findings 清单</h2>
    <p class="meta">
      主交付物为带标注 Excel 副本（首 sheet <strong>{_esc(COMMENTS_SHEET_NAME)}</strong> 汇总附注）。
      本页仅作浏览器快速浏览。
    </p>
    <div class="stats">
      <span class="badge overall">整体 {_esc(stats['overall_severity'])}</span>
      <span class="badge">合计 {stats['finding_count']} 条</span>
      <span class="badge sev-fail">FAIL {stats['fail_count']}</span>
      <span class="badge sev-warn">WARN {stats['warn_count']}</span>
      <span class="badge sev-nr">NEED_REVIEW {stats['need_review_count']}</span>
    </div>
    <table id="findings-table">
      <thead><tr>
        <th>#</th><th>级别</th><th>判断来源</th><th>程序</th><th>工作表</th>
        <th>单元格</th><th>规则</th><th>说明</th>
      </tr></thead>
      <tbody>{rows or '<tr><td colspan="8">无 findings（均为 PASS）</td></tr>'}</tbody>
    </table>
  </section>
    """


def export_review_html(report: QcReport, path: str | Path) -> None:
    """生成精简 findings HTML（与标注底稿副本配套）。"""
    path = Path(path)
    stats = comments_summary_stats(report)

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>固定资产质检 — Findings</title>
  <style>
    body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 24px; background: #f6f7f9; }}
    h1 {{ font-size: 1.35rem; margin-bottom: 8px; }}
    .card {{ background: #fff; border-radius: 8px; padding: 16px 20px; margin: 16px 0;
             box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 14px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #eef1f6; position: sticky; top: 0; }}
    .meta {{ color: #555; font-size: 13px; }}
    .stats {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }}
    .badge {{ padding: 4px 10px; border-radius: 4px; background: #eef; font-size: 13px; }}
    .badge.overall {{ background: #dde; font-weight: 600; }}
    tr.sev-fail td:nth-child(2) {{ color: #b00020; }}
    tr.sev-warn td:nth-child(2) {{ color: #9a6b00; }}
    tr.sev-nr td:nth-child(2) {{ color: #005a9e; }}
    code {{ font-size: 12px; }}
  </style>
</head>
<body>
  <h1>固定资产质检 — Findings</h1>
  <p class="meta">源文件：<code>{_esc(report.source_file)}</code></p>
  <p class="meta">标注底稿：首 sheet「{_esc(COMMENTS_SHEET_NAME)}」附注合计 {stats['finding_count']} 条</p>
  {_findings_only_html(report)}
</body>
</html>
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(html_doc)
