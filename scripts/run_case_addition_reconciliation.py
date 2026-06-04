#!/usr/bin/env python
"""案例库 addition_rollforward_reconciliation 批量回归。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from ingest.case_library import (  # noqa: E402
    case_label,
    find_case_library_dir,
    iter_case_workbooks,
)
from ingest.rollforward_sheet import get_movement_transaction_amount  # noqa: E402
from ingest.workbook_context import load_workbook_context  # noqa: E402
from report.pipeline import run_workbook_qc  # noqa: E402
from rules.addition_common import sum_purchase_original_value  # noqa: E402


def _run_one(path: Path) -> dict:
    label = case_label(path)
    row: dict = {"label": label, "file": path.name}
    t0 = time.perf_counter()
    try:
        ctx = load_workbook_context(path)
        report = run_workbook_qc(ctx, llm=False)
        elapsed = round(time.perf_counter() - t0, 2)
        add = ctx.addition_list
        rf = ctx.rollforward
        mapped = {m.standard_field for m in add.mapped_fields} if add else set()
        list_total, list_count = (
            sum_purchase_original_value(add.records, mapped) if add else (None, 0)
        )
        rf_purchase, rf_row = get_movement_transaction_amount(
            rf,
            transaction_key="purchase",
            measure="original_value",
        )
        issues = [
            i for i in report.issues if i.rule_id == "addition_rollforward_reconciliation"
        ]
        row.update(
            {
                "elapsed_s": elapsed,
                "overall": report.summary.overall_severity.value,
                "issue_total": len(report.issues),
                "addition_sheet": add.source_sheet if add else None,
                "addition_records": len(add.records) if add else 0,
                "list_purchase_total": str(list_total) if list_total is not None else None,
                "list_purchase_rows": list_count,
                "rollforward_sheet": rf.source_sheet if rf else None,
                "rf_purchase_amount": str(rf_purchase) if rf_purchase is not None else None,
                "rf_purchase_row": rf_row,
                "movement_txn_count": len(rf.movement_transactions) if rf else 0,
                "movement_labels": sorted(
                    {t.transaction_label for t in (rf.movement_transactions or [])}
                )
                if rf
                else [],
                "recon_issue_count": len(issues),
                "recon_severities": [i.severity.value for i in issues],
                "recon_messages": [i.message for i in issues],
            }
        )
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _render_md(rows: list[dict], case_dir: Path | None) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 案例库 addition_rollforward_reconciliation 回归",
        "",
        f"- 案例库：`{case_dir}`" if case_dir else "- 案例库：未找到",
        f"- 生成时间：{ts}",
        "",
        "| 案例 | 新增清单 | 清单购置合计 | K.01 购置 | 勾稽结论 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        if r.get("skipped"):
            lines.append(
                f"| {r['label']} | 跳过 | — | — | {r.get('skip_reason', '')} | — |"
            )
            continue
        if r.get("error"):
            lines.append(f"| {r['label']} | 错误 | — | — | {r['error']} | — |")
            continue
        if r["recon_issue_count"] == 0:
            verdict = "PASS（一致或未触发）"
        else:
            msg = r["recon_messages"][0]
            if len(msg) > 72:
                msg = msg[:72] + "…"
            verdict = f"{r['recon_severities'][0]}：{msg}"
        add_desc = f"{r.get('addition_sheet') or '无'} ({r.get('addition_records', 0)}行)"
        lines.append(
            "| {label} | {add} | {lst} | {rf} | {verdict} | {elapsed} |".format(
                label=r["label"],
                add=add_desc,
                lst=r.get("list_purchase_total") or "—",
                rf=r.get("rf_purchase_amount") or "—",
                verdict=verdict,
                elapsed=r.get("elapsed_s"),
            )
        )
    lines.extend(["", "## 明细", ""])
    for r in rows:
        if r.get("skipped"):
            lines.append(f"### {r['label']} — 跳过 ({r.get('skip_reason')})")
            lines.append("")
            continue
        if r.get("error"):
            lines.append(f"### {r['label']} — {r['file']}")
            lines.append(f"- 错误：{r['error']}")
            lines.append("")
            continue
        lines.append(f"### {r['label']} — {r['file']}")
        lines.append(
            f"- 整体结论：{r.get('overall')}；findings 总数：{r.get('issue_total')}"
        )
        lines.append(
            f"- movement 交易行：{r.get('movement_labels')}（共 {r.get('movement_txn_count')} 条）"
        )
        if r.get("recon_messages"):
            for m in r["recon_messages"]:
                lines.append(f"- **addition_rollforward_reconciliation**：{m}")
        else:
            lines.append("- **addition_rollforward_reconciliation**：无 issue")
        lines.append("")
    lines.append("复跑：`python scripts/run_case_addition_reconciliation.py`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="案例库 addition_rollforward_reconciliation 批量回归"
    )
    parser.add_argument("--root", type=Path, default=_ROOT)
    args = parser.parse_args()

    case_dir = find_case_library_dir(args.root)
    if case_dir is None:
        print("未找到案例库目录（固定资产质检agent/案例库）", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for ref in iter_case_workbooks(args.root):
        row = {
            "label": case_label(ref.path),
            "file": ref.path.name,
            "size_mb": ref.size_mb,
            "skipped": ref.skipped,
        }
        if ref.skipped:
            row["skip_reason"] = ref.skip_reason
        else:
            row.update(_run_one(ref.path))
        rows.append(row)

    art = args.root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    json_path = art / "case_addition_reconciliation.json"
    md_path = art / "case_addition_reconciliation.md"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(rows, case_dir), encoding="utf-8")
    print(md_path.read_text(encoding="utf-8"))
    print(f"Wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
