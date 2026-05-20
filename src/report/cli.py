"""命令行：fa-qc-run — 读取底稿/清单 → 质检 → 输出 JSON 报告。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ingest.records import (
    FaListDataset,
    load_fa_list_csv,
    load_fa_list_from_workbook,
)
from llm.config import LlmConfigError, load_llm_config
from report.export_json import export_report_json
from report.export_review_html import export_review_html
from report.pipeline import run_input_qc


def load_input(path: Path, *, sheet_name: str | None = None) -> FaListDataset:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_fa_list_csv(path)
    if suffix in (".xlsx", ".xlsm"):
        return load_fa_list_from_workbook(path, sheet_name=sheet_name)
    raise ValueError(f"不支持的输入格式: {suffix}（请使用 .csv / .xlsx / .xlsm）")


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_qc_report.json")


def review_html_path_for(json_path: Path) -> Path:
    stem = json_path.stem
    if stem.endswith("_qc_report"):
        stem = stem[: -len("_qc_report")] + "_qc_review"
    else:
        stem = stem + "_qc_review"
    return json_path.with_name(stem + ".html")


def print_summary(report, output_path: Path) -> None:
    s = report.summary
    print(f"Overall: {s.overall_severity.value}")
    print(
        f"Records: {s.total_records}  "
        f"PASS: {s.pass_count}  WARN: {s.warn_count}  "
        f"FAIL: {s.fail_count}  NEED_REVIEW: {s.need_review_count}"
    )
    print(f"Issues: {len(report.issues)}")
    if report.issues:
        by_code: dict[str, int] = {}
        for issue in report.issues:
            code = issue.dict_rule_code or issue.rule_id
            by_code[code] = by_code.get(code, 0) + 1
        codes = ", ".join(f"{k}={v}" for k, v in sorted(by_code.items()))
        print(f"By dict_rule_code: {codes}")
    if getattr(report, "summary_sheet_section", None):
        sec = report.summary_sheet_section
        psp = (sec or {}).get("psp_completion") or {}
        print(
            f"汇总页: sheet={sec.get('source_sheet')!r} 程序行={sec.get('program_count')} "
            f"layout={sec.get('layout')!r} | AE-003: {psp.get('overall_severity')} "
            f"({psp.get('issue_count', 0)} findings)"
        )
    if getattr(report, "llm_enrichment", None):
        le = report.llm_enrichment
        if le.error:
            print(f"LLM: error — {le.error}")
        elif le.executive_summary:
            print(f"LLM summary: {le.executive_summary[:200]}{'...' if len(le.executive_summary) > 200 else ''}")
    if getattr(report, "manual_review_sections", None):
        n = len(report.manual_review_sections)
        print(f"Manual review sections: {n} (AE-001 PM/TE/SAD, AE-002 CRA/TT)")
    print(f"Report JSON: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="固定资产质检：读取 FA list（CSV/Excel）并输出 JSON 质检报告",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="底稿 Excel（.xlsx/.xlsm）或脱敏 FA list CSV",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="JSON 报告路径（默认：<输入文件名>_qc_report.json）",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="指定 FA list 工作表名称（仅 Excel）",
    )
    parser.add_argument(
        "--summary-sheet",
        default=None,
        help="指定汇总工作表名称（仅 Excel，默认自动识别）",
    )
    parser.add_argument(
        "--lead-sheet",
        default=None,
        help="指定 K.00 Lead 工作表名称（仅 Excel，默认自动识别）",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="不生成人工核对 HTML 报告",
    )
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--llm",
        action="store_true",
        help="启用大模型 API 增强（需 FA_QC_LLM_API_KEY）",
    )
    llm_group.add_argument(
        "--no-llm",
        action="store_true",
        help="禁用大模型（覆盖环境变量 FA_QC_LLM_ENABLED）",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.is_file():
        print(f"文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        dataset = load_input(input_path, sheet_name=args.sheet)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    is_excel = input_path.suffix.lower() in (".xlsx", ".xlsm")
    if is_excel and not dataset.records:
        print(
            "警告: 未识别到 FA list；若底稿仅有汇总页，将继续检查汇总。",
            file=sys.stderr,
        )

    if args.llm:
        llm_flag: bool | None = True
    elif args.no_llm:
        llm_flag = False
    else:
        llm_flag = None

    try:
        if llm_flag is not None:
            load_llm_config(cli_enabled=llm_flag)
        if is_excel:
            report = run_input_qc(
                str(input_path),
                fa_sheet=args.sheet,
                summary_sheet=args.summary_sheet,
                lead_sheet=args.lead_sheet,
                llm=llm_flag,
            )
        else:
            if not dataset.records:
                print("CSV 无有效数据行。", file=sys.stderr)
                sys.exit(2)
            report = run_input_qc(str(input_path), llm=llm_flag)
    except LlmConfigError as e:
        print(str(e), file=sys.stderr)
        sys.exit(4)
    output_path = (args.output or default_output_path(input_path)).resolve()
    export_report_json(report, output_path)
    if not args.no_html:
        html_path = review_html_path_for(output_path).resolve()
        export_review_html(report, html_path)
        print(f"Review HTML: {html_path}")
    print_summary(report, output_path)

    if report.summary.overall_severity.value == "FAIL":
        sys.exit(3)


if __name__ == "__main__":
    main()
