#!/usr/bin/env python
"""E/F/G 及未诊断案例：与 B/C/D 相同思路的只读诊断。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from ingest.case_library import case_label, iter_case_workbooks  # noqa: E402
from ingest.models import SheetKind  # noqa: E402
from ingest.rollforward_sheet import load_rollforward_from_workbook  # noqa: E402
from ingest.sheet_loader import find_sheets_by_kind  # noqa: E402
from ingest.workbook_context import load_workbook_context  # noqa: E402
from ingest.workbook_structure import analyze_workbook_structure  # noqa: E402
from rules.addition_common import sum_purchase_original_value  # noqa: E402

SKIP_LABELS = frozenset({"B", "C", "D"})


def _misclassified_addition(st) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for s in st.sheets_by_kind.get("rollforward", []):
        if "新增" in s.sheet_name or "清单" in s.sheet_name:
            out.append((s.sheet_name, round(s.confidence, 2)))
    return out


def main() -> int:
    rows: list[dict] = []
    for ref in iter_case_workbooks(_ROOT):
        if ref.skipped or ref.path.name.startswith("~$"):
            continue
        label = case_label(ref.path)
        if label in SKIP_LABELS:
            continue

        st = analyze_workbook_structure(ref.path, max_rows=150)
        dup = [i.message for i in st.issues if i.code.value == "duplicate_sheet_kind"]
        add_sheets = st.sheets_by_kind.get("addition_list", [])
        rf = load_rollforward_from_workbook(ref.path, max_rows=150)
        purchases = [
            {
                "row": t.source_row,
                "label": t.transaction_label,
                "measure": t.measure,
                "amount": str(t.amount),
            }
            for t in rf.movement_transactions
            if t.transaction_key == "purchase"
        ]
        ctx = load_workbook_context(ref.path)
        add = ctx.addition_list
        mapped = {m.standard_field for m in add.mapped_fields} if add else set()
        lst, cnt = sum_purchase_original_value(add.records, mapped) if add else (None, 0)
        add_cands = find_sheets_by_kind(ref.path, SheetKind.ADDITION_LIST, max_rows=150)

        row = {
            "label": label,
            "file": ref.path.name,
            "dup_issues": dup,
            "addition_list_sheets": [
                (s.sheet_name, round(s.confidence, 2)) for s in add_sheets
            ],
            "addition_mis_as_rollforward": _misclassified_addition(st),
            "addition_candidates": [
                (c.sheet_name, round(c.confidence, 2)) for c in add_cands
            ],
            "chosen_addition": add.source_sheet if add else None,
            "addition_records": len(add.records) if add else 0,
            "list_purchase_total": str(lst) if lst is not None else None,
            "list_purchase_rows": cnt,
            "chosen_k01": rf.source_sheet,
            "k01_purchase_rows": purchases,
            "rollforward_all": [
                (s.sheet_name, round(s.confidence, 2))
                for s in st.sheets_by_kind.get("rollforward", [])
            ],
            "fa_list_all": [
                (s.sheet_name, round(s.confidence, 2))
                for s in st.sheets_by_kind.get("fa_list", [])
            ],
            "lead_all": [
                (s.sheet_name, round(s.confidence, 2))
                for s in st.sheets_by_kind.get("lead", [])
            ],
            "summary_all": [
                (s.sheet_name, round(s.confidence, 2))
                for s in st.sheets_by_kind.get("summary", [])
            ],
        }
        rows.append(row)

    out = _ROOT / "artifacts" / "case_efg_diagnosis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in rows:
        print("=" * 60)
        print(r["label"], "-", r["file"])
        if r["dup_issues"]:
            print("DUPLICATE:")
            for m in r["dup_issues"][:5]:
                print(" ", m)
        print("addition_list:", r["addition_list_sheets"])
        print("addition misclassified as rollforward:", r["addition_mis_as_rollforward"])
        print("addition candidates:", r["addition_candidates"])
        print(
            "chosen addition:",
            r["chosen_addition"],
            "records",
            r["addition_records"],
            "purchase",
            r["list_purchase_total"],
            "(%s rows)" % r["list_purchase_rows"],
        )
        print("chosen K01:", r["chosen_k01"])
        print("K01 purchase hits:", r["k01_purchase_rows"])
        print("all rollforward:", r["rollforward_all"][:8])
        print("fa_list:", r["fa_list_all"][:6])
        print("lead:", r["lead_all"])
        print("summary:", r["summary_all"])

    print("WROTE", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
