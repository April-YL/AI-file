"""质检 issue 的 procedure_code 展示名（UI / HTML 共用）。"""

from __future__ import annotations

# UI Findings 分块顺序（质检员工作流）
FINDING_UI_GROUPS: tuple[tuple[str, str], ...] = (
    ("SUMMARY", "汇总页 (PSP / AE-003)"),
    ("K.00", "K.00 Lead"),
    ("FA_LIST", "FA 清单"),
    ("K.01", "K.01 后推"),
    ("K.02.1", "K.02.1 新增测试"),
    ("K.02.1a", "K.02.1a 新增选样输出"),
    ("K.02.2", "K.02.2 处置测试"),
    ("K.02.2a", "K.02.2a 处置选样输出"),
    ("K.03.1", "K.03.1 SAP"),
    ("K.03.2", "K.03.2 TOD"),
    ("K.03.3", "K.03.3 折旧政策复核"),
)

PROCEDURE_LABELS: dict[str, str] = {
    "K.00": "K.00 Lead",
    "SUMMARY": "汇总页 (PSP / AE-003)",
    "FA_LIST": "FA 清单",
    "K.01": "K.01 后推",
    "K.02.1": "K.02.1 新增测试",
    "K.02.1a": "K.02.1a 新增选样输出",
    "K.02.2": "K.02.2 处置测试",
    "K.02.2a": "K.02.2a 处置选样输出",
    "K.03.1": "K.03.1 SAP",
    "K.03.2": "K.03.2 TOD",
    "K.03.3": "K.03.3 折旧政策复核",
    "GLOBAL": "全局",
    "WORKBOOK": "整本底稿",
}


def procedure_label(code: str | None) -> str:
    if not code:
        return "—"
    return PROCEDURE_LABELS.get(code, code)


def procedure_filter_options(codes: list[str]) -> list[tuple[str, str]]:
    """返回 ``(code, label)``，含 ``ALL``。"""
    unique = sorted(set(c for c in codes if c))
    return [("ALL", "全部程序")] + [(c, procedure_label(c)) for c in unique]


def group_findings_by_procedure(
    issues: list[dict[str, object]],
) -> list[tuple[str, str, list[dict[str, object]]]]:
    buckets: dict[str, list[dict[str, object]]] = {code: [] for code, _ in FINDING_UI_GROUPS}
    other: list[dict[str, object]] = []
    known = {code for code, _ in FINDING_UI_GROUPS}
    for issue in issues:
        if issue.get("severity") == "PASS":
            continue
        pc = str(issue.get("procedure_code") or "")
        if pc in known:
            buckets[pc].append(issue)
        else:
            other.append(issue)
    out: list[tuple[str, str, list[dict[str, object]]]] = [
        (code, label, buckets[code]) for code, label in FINDING_UI_GROUPS if buckets[code]
    ]
    if other:
        out.append(("_other", "其他", other))
    return out
