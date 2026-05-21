from __future__ import annotations

from datetime import date, datetime

from rules.parsing import is_blank

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y年%m月%d日",
)


def parse_lead_date(value: str | None) -> date | None:
    """解析 Lead 基础信息中的日期字段（ingest 多为 ISO 字符串）。"""
    if is_blank(value):
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
