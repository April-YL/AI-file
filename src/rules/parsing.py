from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ingest.models import AssetRecord

_CURRENCY_CHARS = re.compile(r"[¥$€￥,\s]")
_PAREN_NEGATIVE = re.compile(r"^\((.+)\)$")


def is_blank(value: str | None) -> bool:
    if value is None:
        return True
    return not str(value).strip()


def parse_amount(value: str | None) -> Decimal | None:
    """解析金额字符串；支持千分位、括号负数、常见货币符号。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in ("-", "—", "N/A", "n/a", "#N/A"):
        return None
    text = _CURRENCY_CHARS.sub("", text)
    paren = _PAREN_NEGATIVE.match(text)
    if paren:
        text = f"-{paren.group(1)}"
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def amount_tolerance(base: Decimal, *, absolute: Decimal = Decimal("0.01")) -> Decimal:
    """勾稽允差：至少 absolute，大额按 0.01% 相对误差。"""
    relative = abs(base) * Decimal("0.0001")
    return max(absolute, relative)


def record_has_identity(record: AssetRecord) -> bool:
    return not is_blank(record.asset_id) or not is_blank(record.asset_name)


def record_is_empty_data_row(
    record: AssetRecord,
    mapped_fields: set[str],
) -> bool:
    """跳过无标识且无核心金额的空行/分隔行。"""
    if record_has_identity(record):
        return False
    for field in ("original_value", "accumulated_depreciation", "net_value"):
        if field in mapped_fields and not is_blank(getattr(record, field, None)):
            return False
    return True
