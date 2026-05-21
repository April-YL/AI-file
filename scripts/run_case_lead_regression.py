#!/usr/bin/env python
"""案例库 Lead 质检批量回归：生成 Markdown + JSON 回归表。

默认跳过 >20MB 及文件名含 A公司/A有限公司 的底稿（A 约 42MB）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# 项目根
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from ingest.case_library import (  # noqa: E402
    DEFAULT_MAX_WORKBOOK_MB,
    case_label,
    find_case_library_dir,
    iter_case_workbooks,
)
from ingest.lead_sheet import load_lead_from_workbook  # noqa: E402
from ingest.rollforward_sheet import load_rollforward_from_workbook  # noqa: E402
from report.lead_sheet_report import build_lead_sheet_section  # noqa: E402
from rules.lead_runner import LEAD_RULE_IDS, run_lead_rules  # noqa: E402
from rules.registry import attach_rule_metadata  # noqa: E402


def _run_one(path: Path) -> dict:
    t0 = time.perf_counter()
    err: str | None = None
    lead = None
    sec: dict | None = None
    try:
        lead = load_lead_from_workbook(path)
        rollforward = load_rollforward_from_workbook(path)
        if not rollforward.source_sheet:
            rollforward = None
        issues = attach_rule_metadata(
            run_lead_rules(lead, rollforward=rollforward)
        )
        sec = build_lead_sheet_section(lead, issues)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    elapsed = round(time.perf_counter() - t0, 2)

    row: dict = {
        "file": path.name,
        "label": case_label(path),
        "elapsed_s": elapsed,
        "error": err,
    }
    if err or lead is None or sec is None:
        row["status"] = "error" if err else "no_lead"
        return row

    qc = sec["lead_qc"]
    rule_sev = {
        rid: qc["rules"][rid]["overall_severity"]
        for rid in LEAD_RULE_IDS
        if rid in qc.get("rules", {})
    }
    sev_counter = Counter(rule_sev.values())

    row.update(
        {
            "status": "ok",
            "lead_sheet": lead.source_sheet,
            "layout_variant": lead.layout_variant,
            "cra_rows": len(lead.cra_rows),
            "movement_rows": len(lead.movement_rows),
            "expectations": len(lead.expectations),
            "blocks_detected": sec.get("blocks_detected", []),
            "overall_severity": qc["overall_severity"],
            "issue_count": qc["issue_count"],
            "rule_severities": rule_sev,
            "fail_rules": [r for r, s in rule_sev.items() if s == "FAIL"],
            "warn_rules": [r for r, s in rule_sev.items() if s == "WARN"],
            "need_review_rules": [r for r, s in rule_sev.items() if s == "NEED_REVIEW"],
            "severity_counts": dict(sev_counter),
        }
    )
    return row


def _markdown_report(
    *,
    case_dir: Path | None,
    max_mb: float,
    skipped: list[dict],
    rows: list[dict],
    generated_at: str,
) -> str:
    lines = [
        "# 案例库 Lead 质检回归表",
        "",
        f"- 生成时间（UTC）：{generated_at}",
        f"- 案例库：`{case_dir}`" if case_dir else "- 案例库：未找到",
        f"- 跳过策略：>{max_mb}MB 或文件名含 A公司/A有限公司",
        "",
        "## 汇总",
        "",
        "| 标签 | 文件 | 状态 | Lead 表 | layout | CRA | Mov | Exp | 整体 | issues | FAIL 规则 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- | ---: |",
    ]
    for r in rows:
        if r.get("status") != "ok":
            lines.append(
                f"| {r.get('label','?')} | {r['file']} | {r['status']} | — | — | — | — | — | — | — | {r.get('error','')} | {r.get('elapsed_s','')} |"
            )
            continue
        fail_short = ", ".join(r["fail_rules"][:3])
        if len(r["fail_rules"]) > 3:
            fail_short += "…"
        lines.append(
            f"| {r['label']} | {r['file']} | ok | {r['lead_sheet']} | {r.get('layout_variant') or '—'} | "
            f"{r['cra_rows']} | {r['movement_rows']} | {r['expectations']} | "
            f"**{r['overall_severity']}** | {r['issue_count']} | {fail_short or '—'} | {r['elapsed_s']} |"
        )

    if skipped:
        lines.extend(["", "## 跳过", ""])
        for s in skipped:
            lines.append(f"- `{s['file']}` ({s['size_mb']} MB) — {s['skip_reason']}")

    lines.extend(["", "## 规则维度（overall_severity）", ""])
    header = "| 标签 | " + " | ".join(LEAD_RULE_IDS) + " |"
    sep = "| --- | " + " | ".join(["---"] * len(LEAD_RULE_IDS)) + " |"
    lines.extend([header, sep])
    for r in rows:
        if r.get("status") != "ok":
            continue
        cells = [r["rule_severities"].get(rid, "—") for rid in LEAD_RULE_IDS]
        lines.append(f"| {r['label']} | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Ingest 基线（手工回归参考）",
            "",
            "| 案例 | cra | mov | exp | layout 备注 |",
            "| --- | ---: | ---: | ---: | --- |",
            "| B–G（标准 SWP） | 5 | 4 | 7 | `layout_variant=None` |",
            "| A（跳过） | 0 | — | — | `no_cra_te_volatility`（大文件未跑） |",
            "",
            "复跑：`python scripts/run_case_lead_regression.py`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="案例库 Lead 质检批量回归")
    parser.add_argument(
        "--max-mb",
        type=float,
        default=DEFAULT_MAX_WORKBOOK_MB,
        help=f"跳过大于该体积的文件（默认 {DEFAULT_MAX_WORKBOOK_MB}）",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "artifacts",
        help="回归表输出目录",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_ROOT,
        help="项目根目录",
    )
    args = parser.parse_args()

    case_dir = find_case_library_dir(args.root)
    if case_dir is None:
        print("未找到案例库目录（固定资产质检agent/案例库）", file=sys.stderr)
        return 1

    refs = iter_case_workbooks(args.root, max_mb=args.max_mb)
    skipped = [
        {
            "file": r.path.name,
            "size_mb": r.size_mb,
            "skip_reason": r.skip_reason,
        }
        for r in refs
        if r.skipped
    ]
    rows: list[dict] = []
    for r in refs:
        if r.skipped:
            continue
        print(f"Run {r.path.name} …", flush=True)
        rows.append(_run_one(r.path))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": generated_at,
        "case_dir": str(case_dir),
        "max_mb": args.max_mb,
        "skipped": skipped,
        "rows": rows,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "case_lead_regression.json"
    md_path = args.out_dir / "case_lead_regression.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(
        _markdown_report(
            case_dir=case_dir,
            max_mb=args.max_mb,
            skipped=skipped,
            rows=rows,
            generated_at=generated_at,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    ok = sum(1 for r in rows if r.get("status") == "ok")
    print(f"Done: {ok} ok, {len(skipped)} skipped, {len(rows) - ok} failed/no_lead")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
