#!/usr/bin/env python
"""案例库 K.01 识别层批量回归：生成 Markdown + JSON 回归表。

默认跳过 >20MB 及文件名含 A公司/A有限公司 的底稿。
"""

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
    DEFAULT_MAX_WORKBOOK_MB,
    case_label,
    find_case_library_dir,
    iter_case_workbooks,
)
from ingest.rollforward_sheet import K01_SECTION_IDS, load_rollforward_from_workbook  # noqa: E402

# 与 handoff / 案例库实测一致
_EXPECTED_SECTIONS = 6
_EXPECTED_PROFILE = "hybrid"


def _run_one(path: Path, *, max_rows: int) -> dict:
    t0 = time.perf_counter()
    err: str | None = None
    rf = None
    try:
        rf = load_rollforward_from_workbook(path, max_rows=max_rows)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    elapsed = round(time.perf_counter() - t0, 2)

    row: dict = {
        "file": path.name,
        "label": case_label(path),
        "elapsed_s": elapsed,
        "error": err,
    }
    if err or rf is None or not rf.source_sheet:
        row["status"] = "error" if err else "no_rollforward"
        return row

    present = sum(1 for sid in K01_SECTION_IDS if rf.section_presence.get(sid))
    row.update(
        {
            "status": "ok",
            "rollforward_sheet": rf.source_sheet,
            "layout_profile": rf.layout_profile.value,
            "has_movement_rows": rf.has_movement_rows,
            "header_row": rf.header_row,
            "total_row": rf.total_row,
            "sections_detected": present,
            "section_presence": dict(rf.section_presence),
            "section_regions": {
                sid: {
                    "anchor_row": reg.anchor_row,
                    "start_row": reg.start_row,
                    "end_row": reg.end_row,
                }
                for sid, reg in rf.section_regions.items()
            },
            "section_conflicts": list(rf.section_conflicts),
            "recognition_confidence": rf.recognition_confidence,
            "ending_totals": {
                k: str(v) for k, v in rf.ending_totals.items() if v is not None
            },
            "notes": rf.notes,
        }
    )
    return row


def _markdown_report(
    *,
    case_dir: Path | None,
    max_mb: float,
    max_rows: int,
    skipped: list[dict],
    rows: list[dict],
    generated_at: str,
) -> str:
    lines = [
        "# 案例库 K.01 识别回归表",
        "",
        f"- 生成时间（UTC）：{generated_at}",
        f"- 案例库：`{case_dir}`" if case_dir else "- 案例库：未找到",
        f"- 跳过策略：>{max_mb}MB 或文件名含 A公司/A有限公司",
        f"- 扫描行数上限：`max_rows={max_rows}`",
        "",
        "## 汇总",
        "",
        "| 标签 | 文件 | 状态 | K.01 表 | profile | 区块 | 置信度 | 冲突 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: |",
    ]
    for r in rows:
        if r.get("status") != "ok":
            lines.append(
                f"| {r.get('label', '?')} | {r['file']} | {r['status']} | — | — | — | — | — | {r.get('elapsed_s', '')} |"
            )
            continue
        conflicts = len(r.get("section_conflicts") or [])
        lines.append(
            f"| {r['label']} | {r['file']} | ok | {r['rollforward_sheet']} | {r['layout_profile']} | "
            f"{r['sections_detected']}/6 | {r['recognition_confidence']} | {conflicts} | {r['elapsed_s']} |"
        )

    if skipped:
        lines.extend(["", "## 跳过", ""])
        for s in skipped:
            lines.append(f"- `{s['file']}` ({s['size_mb']} MB) — {s['skip_reason']}")

    lines.extend(
        [
            "",
            "## 基线期望（B–G）",
            "",
            f"- `layout_profile` = `{_EXPECTED_PROFILE}`",
            f"- `sections_detected` = {_EXPECTED_SECTIONS}",
            "- 六区块命中后允许存在 `duplicate_anchor` 等冲突（见 `section_conflicts`）",
            "",
            "复跑：`python scripts/run_case_rollforward_regression.py`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="案例库 K.01 识别层批量回归")
    parser.add_argument("--max-mb", type=float, default=DEFAULT_MAX_WORKBOOK_MB)
    parser.add_argument("--max-rows", type=int, default=150, help="每表读取行数上限")
    parser.add_argument("--out-dir", type=Path, default=_ROOT / "artifacts")
    parser.add_argument("--root", type=Path, default=_ROOT)
    args = parser.parse_args()

    case_dir = find_case_library_dir(args.root)
    if case_dir is None:
        print("未找到案例库目录（固定资产质检agent/案例库）", file=sys.stderr)
        return 1

    refs = iter_case_workbooks(args.root, max_mb=args.max_mb)
    skipped = [
        {"file": r.path.name, "size_mb": r.size_mb, "skip_reason": r.skip_reason}
        for r in refs
        if r.skipped
    ]
    rows: list[dict] = []
    for r in refs:
        if r.skipped:
            continue
        print(f"Run {r.path.name} …", flush=True)
        rows.append(_run_one(r.path, max_rows=args.max_rows))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": generated_at,
        "case_dir": str(case_dir),
        "max_mb": args.max_mb,
        "max_rows": args.max_rows,
        "expected_profile": _EXPECTED_PROFILE,
        "expected_sections": _EXPECTED_SECTIONS,
        "skipped": skipped,
        "rows": rows,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "case_rollforward_regression.json"
    md_path = args.out_dir / "case_rollforward_regression.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        _markdown_report(
            case_dir=case_dir,
            max_mb=args.max_mb,
            max_rows=args.max_rows,
            skipped=skipped,
            rows=rows,
            generated_at=generated_at,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    ok = sum(1 for r in rows if r.get("status") == "ok")
    print(f"Done: {ok} ok, {len(skipped)} skipped, {len(rows) - ok} failed/no_rollforward")
    return 0 if ok == len(rows) and rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
