"""质检 issue 的 procedure_code 展示名（UI / HTML 共用）。"""

from __future__ import annotations

# UI Findings 分块顺序（质检员工作流）
FINDING_UI_GROUPS: tuple[tuple[str, str], ...] = (
    ("SUMMARY", "汇总页 (PSP / AE-003)"),
    ("K.00", "K.00 Lead"),
    ("FA_LIST", "FA 清单"),
    ("K.01", "K.01 后推"),
    ("K.02", "K.02 新增/处置"),
)

PROCEDURE_LABELS: dict[str, str] = {
    "K.00": "K.00 Lead",
    "SUMMARY": "汇总页 (PSP / AE-003)",
    "FA_LIST": "FA 清单",
    "K.01": "K.01 后推",
    "K.02": "K.02 新增/处置",
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
