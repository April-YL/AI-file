"""K.02 新增/处置测试底稿轻量读取（程序包门控用）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import openpyxl

from ingest.workbook_reader import read_worksheet_rows

K02Kind = Literal["addition", "disposal"]

_LIMITED_EXECUTION_MARKERS = (
    "不执行",
    "未执行",
    "无需执行",
    "无须执行",
    "未抽样",
    "未选样",
    "未进行抽样",
    "未开展",
    "本期无新增",
    "本期无处置",
    "无新增固定资产",
    "无处置固定资产",
    "无处置",
    "无新增",
    "小于te",
    "低于te",
    "小于 te",
    "低于 te",
    "小于tt",
    "低于tt",
    "净值小于",
    "原值小于",
    "不执行本次",
    "未执行本次",
    "limited scope",
    "not performed",
)

_WAIVER_SNIPPET_MAX = 120


def _norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value).lower())


def find_k02_test_sheet_title(
    titles: list[str],
    *,
    kind: K02Kind,
) -> str | None:
    """从工作簿表名中定位 K.02.1 / K.02.2 测试底稿（非清单、非选样输出）。"""
    for title in titles:
        if _is_k02_test_sheet_title(title, kind=kind):
            return title
    return None


def _is_k02_test_sheet_title(title: str, *, kind: K02Kind) -> bool:
    text = _norm_title(title)
    raw = title.strip().lower()
    if kind == "disposal":
        if _is_disposal_list_title(title) or _is_disposal_sampling_title(title):
            return False
        return (
            "k022" in text
            or (
                any(x in title for x in ("处置", "减少", "报废"))
                and any(x in title for x in ("测试", "细节", "detail"))
            )
            or ("disposal" in raw and any(x in raw for x in ("test", "detail")))
        )
    if _is_addition_list_title(title) or _is_addition_sampling_title(title):
        return False
    return (
        "k021" in text
        or ("新增" in title and any(x in title for x in ("测试", "细节", "detail")))
        or ("addition" in raw and any(x in raw for x in ("test", "detail")))
    )


def _is_disposal_list_title(title: str) -> bool:
    text = _norm_title(title)
    raw = title.strip().lower()
    return (
        "处置清单" in title
        or "减少清单" in title
        or ("处置" in title and "清单" in title)
        or ("减少" in title and "清单" in title)
        or ("k022b" in text and any(x in title for x in ("处置", "减少", "报废")))
        or ("disposal" in raw and "list" in raw)
    )


def _is_addition_list_title(title: str) -> bool:
    text = _norm_title(title)
    raw = title.strip().lower()
    return (
        "新增清单" in title
        or ("新增" in title and "清单" in title)
        or ("k021b" in text and "新增" in title)
        or ("addition" in raw and "list" in raw)
    )


def _is_disposal_sampling_title(title: str) -> bool:
    text = _norm_title(title)
    raw = title.strip().lower()
    return (
        "k022a" in text
        or (
            any(x in title for x in ("处置", "减少", "报废"))
            and any(x in title for x in ("选样", "抽样"))
            and any(x in title for x in ("输出", "结果"))
        )
        or (
            "disposal" in raw
            and any(x in raw for x in ("sample", "sampling"))
            and any(x in raw for x in ("output", "result"))
        )
    )


def _is_addition_sampling_title(title: str) -> bool:
    text = _norm_title(title)
    raw = title.strip().lower()
    return (
        "k021a" in text
        or (
            "新增" in title
            and any(x in title for x in ("选样", "抽样"))
            and any(x in title for x in ("输出", "结果"))
        )
        or "抽样输出" in title
        or "选样输出" in title
        or (
            "addition" in raw
            and any(x in raw for x in ("sample", "sampling"))
            and any(x in raw for x in ("output", "result"))
        )
    )


def _normalize_blob(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _extract_limited_execution_snippet(blob: str) -> str | None:
    normalized = _normalize_blob(blob)
    if not normalized:
        return None
    for marker in _LIMITED_EXECUTION_MARKERS:
        if _normalize_blob(marker) not in normalized:
            continue
        for line in re.split(r"[\r\n]+", blob):
            line = line.strip()
            if not line:
                continue
            if _normalize_blob(marker) in _normalize_blob(line):
                return line[:_WAIVER_SNIPPET_MAX]
        return marker
    return None


def extract_limited_execution_note_from_rows(
    rows: list[tuple],
    *,
    max_scan_rows: int = 80,
) -> str | None:
    """扫描测试底稿前若干行，提取不执行/受限执行说明。"""
    chunks: list[str] = []
    for row in rows[:max_scan_rows]:
        for cell in row:
            if cell is None:
                continue
            text = str(cell).strip()
            if len(text) >= 4:
                chunks.append(text)
    if not chunks:
        return None
    return _extract_limited_execution_snippet("\n".join(chunks))


def read_k02_limited_execution_note(
    path: str | Path,
    titles: list[str],
    *,
    kind: K02Kind,
    max_rows: int = 80,
) -> str | None:
    """读取 K.02 测试 sheet 中的受限执行/不执行说明（供程序包门控）。"""
    sheet_name = find_k02_test_sheet_title(titles, kind=kind)
    if sheet_name is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            return None
        rows = read_worksheet_rows(wb[sheet_name], max_rows=max_rows)
    finally:
        wb.close()
    return extract_limited_execution_note_from_rows(rows)
