from __future__ import annotations

import re
from collections.abc import Sequence

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from rules.models import QcIssue, Severity
from rules.psp_completion import normalize_execution_status

RULE_ID = "addition_test_package_complete"
DISPOSAL_RULE_ID = "disposal_test_package_complete"


def check_addition_test_package(
    summary: SummarySheetDataset | None,
    *,
    workbook_sheet_titles: Sequence[str] | None,
) -> list[QcIssue]:
    """检查新增测试执行时是否形成新增清单/测试表/抽样输出三表链条。"""
    if summary is None or not summary.programs or not workbook_sheet_titles:
        return []
    return _check_k02_package(
        summary,
        workbook_sheet_titles=workbook_sheet_titles,
        kind="addition",
    )


def check_disposal_test_package(
    summary: SummarySheetDataset | None,
    *,
    workbook_sheet_titles: Sequence[str] | None,
) -> list[QcIssue]:
    """检查处置测试执行时是否形成处置清单/测试表/抽样输出三表链条。"""
    if summary is None or not summary.programs or not workbook_sheet_titles:
        return []
    return _check_k02_package(
        summary,
        workbook_sheet_titles=workbook_sheet_titles,
        kind="disposal",
    )


def _check_k02_package(
    summary: SummarySheetDataset,
    *,
    workbook_sheet_titles: Sequence[str],
    kind: str,
) -> list[QcIssue]:
    spec = _package_spec(kind)
    if not _test_marked_executed(summary.programs, kind=kind):
        return []

    evidence = _find_package_sheets(workbook_sheet_titles, kind=kind)
    missing = [label for label, title in evidence.items() if title is None]
    if not missing:
        return []

    severity = Severity.FAIL if len(missing) >= 2 else Severity.NEED_REVIEW
    found = [f"{label}: {title}" for label, title in evidence.items() if title]
    return [
        QcIssue(
            asset_id=None,
            rule_id=spec["rule_id"],
            field=spec["field"],
            severity=severity,
            message=(
                f"汇总页显示{spec['name']}已执行，但未识别到完整的{spec['name']}程序包；"
                f"缺少：{'、'.join(missing)}"
                + (f"；已识别：{'；'.join(found)}" if found else "")
            ),
            suggestion=(
                f"核对是否存在{spec['list_label']}、{spec['test_label']}和抽样/选样输出结果；"
                "如使用合并页或其他命名，请在底稿或汇总页中保留可识别的索引说明。"
            ),
            procedure_code=spec["procedure_code"],
            source_sheet=summary.source_sheet or "汇总",
            source_row=_first_execution_row(summary.programs, kind=kind),
        )
    ]


def _package_spec(kind: str) -> dict[str, str]:
    if kind == "disposal":
        return {
            "rule_id": DISPOSAL_RULE_ID,
            "field": "disposal_test_package",
            "name": "处置测试",
            "list_label": "处置清单",
            "test_label": "处置测试底稿",
            "procedure_code": "K.02.2",
        }
    return {
        "rule_id": RULE_ID,
        "field": "addition_test_package",
        "name": "新增测试",
        "list_label": "新增清单",
        "test_label": "新增测试底稿",
        "procedure_code": "K.02.1",
    }


def _test_marked_executed(programs: list[PspProgramRow], *, kind: str) -> bool:
    inherited = _inherit_k02_status(programs, kind=kind)
    for idx, row in enumerate(programs):
        if not _is_k02_test_row(row, kind=kind):
            continue
        status = normalize_execution_status(inherited.get(idx, row.execution_status))
        if status == "yes":
            return True
    return False


def _first_execution_row(programs: list[PspProgramRow], *, kind: str) -> int | None:
    inherited = _inherit_k02_status(programs, kind=kind)
    for idx, row in enumerate(programs):
        if _is_k02_test_row(row, kind=kind) and normalize_execution_status(
            inherited.get(idx, row.execution_status)
        ) == "yes":
            return row.source_row
    return None


def _inherit_k02_status(programs: list[PspProgramRow], *, kind: str) -> dict[int, str]:
    pairs = [
        (idx, row)
        for idx, row in enumerate(programs)
        if _is_k02_group_row(row, kind=kind)
    ]
    pairs.sort(key=lambda p: p[1].source_row or 0)
    status = next(((row.execution_status or "").strip() for _, row in pairs if (row.execution_status or "").strip()), "")
    if not status:
        return {}
    return {idx: status for idx, row in pairs if not (row.execution_status or "").strip()}


def _is_k02_test_row(row: PspProgramRow, *, kind: str) -> bool:
    text = _norm(f"{row.procedure_name} {row.sheet_ref or ''}")
    if kind == "disposal":
        if "k022" in text or "k022a" in text:
            return True
        return any(x in text for x in ("处置", "减少", "报废")) and any(
            x in text for x in ("测试", "细节", "选样", "抽样")
        )
    if "k021" in text or "k021a" in text:
        return True
    return "新增" in text and any(x in text for x in ("测试", "细节", "选样", "抽样"))


def _is_k02_group_row(row: PspProgramRow, *, kind: str) -> bool:
    text = _norm(f"{row.procedure_name} {row.sheet_ref or ''}")
    if kind == "disposal":
        return "k022" in text or "k022a" in text
    return "k021" in text or "k021a" in text


def _find_package_sheets(titles: Sequence[str], *, kind: str) -> dict[str, str | None]:
    if kind == "disposal":
        evidence: dict[str, str | None] = {
            "处置清单": None,
            "处置测试": None,
            "抽样输出结果": None,
        }
    else:
        evidence = {
            "新增清单": None,
            "新增测试": None,
            "抽样输出结果": None,
        }
    for title in titles:
        list_label = "处置清单" if kind == "disposal" else "新增清单"
        test_label = "处置测试" if kind == "disposal" else "新增测试"
        if evidence[list_label] is None and _is_list_title(title, kind=kind):
            evidence[list_label] = title
        if evidence[test_label] is None and _is_test_title(title, kind=kind):
            evidence[test_label] = title
        if evidence["抽样输出结果"] is None and _is_sampling_output_title(title, kind=kind):
            evidence["抽样输出结果"] = title
    return evidence


def _is_list_title(title: str, *, kind: str) -> bool:
    text = _norm(title)
    raw = title.strip().lower()
    if kind == "disposal":
        return (
            "处置清单" in title
            or "减少清单" in title
            or ("处置" in title and "清单" in title)
            or ("减少" in title and "清单" in title)
            or ("k022b" in text and any(x in title for x in ("处置", "减少", "报废")))
            or ("disposal" in raw and "list" in raw)
        )
    return (
        "新增清单" in title
        or ("新增" in title and "清单" in title)
        or ("k021b" in text and "新增" in title)
        or ("addition" in raw and "list" in raw)
    )


def _is_test_title(title: str, *, kind: str) -> bool:
    text = _norm(title)
    raw = title.strip().lower()
    if _is_list_title(title, kind=kind) or _is_sampling_output_title(title, kind=kind):
        return False
    if kind == "disposal":
        return (
            "k022" in text
            or (any(x in title for x in ("处置", "减少", "报废")) and any(x in title for x in ("测试", "细节", "detail")))
            or ("disposal" in raw and any(x in raw for x in ("test", "detail")))
        )
    return (
        "k021" in text
        or ("新增" in title and any(x in title for x in ("测试", "细节", "detail")))
        or ("addition" in raw and any(x in raw for x in ("test", "detail")))
    )


def _is_sampling_output_title(title: str, *, kind: str) -> bool:
    text = _norm(title)
    raw = title.strip().lower()
    if kind == "disposal":
        return (
            "k022a" in text
            or (any(x in title for x in ("处置", "减少", "报废")) and any(x in title for x in ("选样", "抽样")) and any(x in title for x in ("输出", "结果")))
            or ("disposal" in raw and any(x in raw for x in ("sample", "sampling")) and any(x in raw for x in ("output", "result")))
        )
    return (
        "k021a" in text
        or ("新增" in title and any(x in title for x in ("选样", "抽样")) and any(x in title for x in ("输出", "结果")))
        or ("抽样输出" in title or "选样输出" in title)
        or ("addition" in raw and any(x in raw for x in ("sample", "sampling")) and any(x in raw for x in ("output", "result")))
    )


def _norm(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value).lower())
