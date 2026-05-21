"""命令行：对案例库或指定 Excel 底稿做读取诊断。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ingest.case_library import (
    DEFAULT_MAX_WORKBOOK_MB,
    find_case_library_dir,
    should_skip_case_workbook,
)
from ingest.workbook_ingest import load_workbook_ingest
from ingest.workbook_reader import diagnose_workbook


def main() -> None:
    parser = argparse.ArgumentParser(description="固定资产底稿读取诊断")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Excel 文件或目录；默认扫描项目下案例库",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=DEFAULT_MAX_WORKBOOK_MB,
        help=f"跳过大于该体积（MB）的文件，默认 {DEFAULT_MAX_WORKBOOK_MB}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="输出整本底稿结构 + 加载摘要 + 勾稽关系（JSON 时合并 ingest 段）",
    )
    args = parser.parse_args()

    files: list[Path] = []
    if args.paths:
        for p in args.paths:
            path = Path(p)
            if path.is_file() and path.suffix.lower() in (".xlsx", ".xlsm"):
                files.append(path)
            elif path.is_dir():
                files.extend(sorted(path.glob("*.xlsx")))
    else:
        root = Path.cwd()
        case_dir = find_case_library_dir(root)
        if case_dir:
            files = sorted(case_dir.glob("*.xlsx"))
        else:
            print("未找到案例库目录，请指定文件路径。", file=sys.stderr)
            sys.exit(1)

    results = []
    for f in files:
        skip_reason = should_skip_case_workbook(f, max_mb=args.max_mb)
        if skip_reason:
            results.append({"path": str(f), "skipped": True, "reason": skip_reason})
            continue
        diag = diagnose_workbook(f)
        item = diag.to_dict()
        if args.ingest:
            ctx = load_workbook_ingest(f)
            item["ingest"] = ctx.to_dict()
        results.append(item)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            if item.get("skipped"):
                print(f"SKIP {item['path']} ({item['reason']})")
                continue
            print(f"\n=== {item['path']} ===")
            for s in item.get("sheets", []):
                if s["kind"] in ("skip",):
                    continue
                line = (
                    f"  [{s['kind']}] {s['sheet_name']} "
                    f"conf={s['confidence']} name={s['name_score']} content={s['content_score']}"
                )
                if s.get("header_row"):
                    line += f" header_row={s['header_row']}"
                print(line)
                if s["kind"] == "fa_list":
                    if s["missing_required"]:
                        print(f"    missing_required: {s['missing_required']}")
                    if s["missing_recommended"]:
                        print(f"    missing_recommended: {s['missing_recommended']}")
                    if s["mapped_fields"]:
                        print(f"    mapped: {len(s['mapped_fields'])} fields")
                if s.get("notes"):
                    for n in s["notes"]:
                        print(f"    note: {n}")


if __name__ == "__main__":
    main()
