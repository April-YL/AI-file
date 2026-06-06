#!/usr/bin/env python
"""案例库 ingest 多期 sheet 路由回归（C/D/F 等双套底稿）。"""

from __future__ import annotations

import argparse
import json
import sys
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
from ingest.lead_sheet import find_lead_sheets  # noqa: E402
from ingest.records import find_fa_list_sheets  # noqa: E402
from ingest.sheet_loader import find_sheets_by_kind  # noqa: E402
from ingest.models import SheetKind  # noqa: E402
from ingest.summary_sheet import find_summary_sheets  # noqa: E402
from ingest.workbook_context import load_workbook_context  # noqa: E402
from rules.addition_common import sum_purchase_original_value  # noqa: E402


def _first_name(candidates, index: int = 0) -> str | None:
    if not candidates:
        return None
    item = candidates[index]
    if hasattr(item, "sheet_name"):
        return item.sheet_name
    return item[0]


def _run_one(path: Path) -> dict:
    label = case_label(path)
    row: dict = {"label": label, "file": path.name}
    try:
        ctx = load_workbook_context(path)
        fa_cands = find_fa_list_sheets(path)
        rf_cands = find_sheets_by_kind(path, SheetKind.ROLLFORWARD)
        sum_cands = find_summary_sheets(path)
        lead_cands = find_lead_sheets(path)
        add_cands = find_sheets_by_kind(path, SheetKind.ADDITION_LIST)

        add = ctx.addition_list
        mapped = {m.standard_field for m in add.mapped_fields} if add else set()
        list_total, list_count = (
            sum_purchase_original_value(add.records, mapped) if add else (None, 0)
        )

        row.update(
            {
                "fa_list_sheet": ctx.fa_list.source_sheet if ctx.fa_list else None,
                "fa_list_candidates": [_first_name(c) for c in fa_cands[:5]],
                "rollforward_sheet": ctx.rollforward.source_sheet if ctx.rollforward else None,
                "rollforward_candidates": [c.sheet_name for c in rf_cands[:5]],
                "summary_sheet": ctx.summary.source_sheet if ctx.summary else None,
                "summary_candidates": [_first_name(c) for c in sum_cands[:5]],
                "lead_sheet": ctx.lead.source_sheet if ctx.lead else None,
                "lead_candidates": [_first_name(c) for c in lead_cands[:5]],
                "addition_sheet": add.source_sheet if add else None,
                "addition_candidates": [c.sheet_name for c in add_cands[:5]],
                "addition_mapped_fields": sorted(mapped),
                "addition_records": len(add.records) if add else 0,
                "list_purchase_total": str(list_total) if list_total is not None else None,
                "list_purchase_rows": list_count,
            }
        )
        for sheet_key in ("rollforward_sheet", "summary_sheet", "lead_sheet", "fa_list_sheet", "addition_sheet"):
            chosen = row.get(sheet_key)
            if chosen and str(chosen).strip().lower().endswith("-24"):
                row[f"{sheet_key}_prior_year"] = True
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="案例库 ingest 多期路由回归")
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--labels", nargs="*", default=None, help="仅跑指定案例标签 C D F")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=_ROOT / "artifacts" / "case_ingest_routing.json",
    )
    args = parser.parse_args()

    case_dir = find_case_library_dir(args.root)
    if case_dir is None:
        print("未找到案例库目录（固定资产质检agent/案例库）", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for ref in iter_case_workbooks(args.root):
        label = case_label(ref.path)
        if args.labels and label not in args.labels:
            continue
        row: dict = {
            "label": label,
            "file": ref.path.name,
            "size_mb": ref.size_mb,
            "skipped": ref.skipped,
        }
        if ref.skipped:
            row["skip_reason"] = ref.skip_reason
        else:
            row.update(_run_one(ref.path))
        rows.append(row)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_dir": str(case_dir),
        "rows": rows,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.json_out} ({len(rows)} cases)")
    for row in rows:
        if row.get("skipped"):
            print(f"{row.get('label')}: skipped ({row.get('skip_reason')})")
            continue
        prior_flags = [
            k
            for k, v in row.items()
            if k.endswith("_prior_year") and v
        ]
        print(
            f"{row.get('label')}: RF={row.get('rollforward_sheet')} "
            f"SUM={row.get('summary_sheet')} ADD={row.get('addition_sheet')} "
            f"purchase_rows={row.get('list_purchase_rows')}"
            + (f" PRIOR={prior_flags}" if prior_flags else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
