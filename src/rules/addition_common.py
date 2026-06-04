"""K.02 新增清单规则共用工具。"""

from __future__ import annotations

from decimal import Decimal

from ingest.models import AssetRecord
from rules.parsing import parse_amount, record_is_empty_data_row

_PURCHASE_TERMS = (
    "购置",
    "采购",
    "购买",
    "新购",
    "外购",
    "purchase",
    "acquisition",
)


def is_purchase_addition_method(value: str | None) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return any(term in text for term in _PURCHASE_TERMS)


def sum_purchase_original_value(
    records: list[AssetRecord],
    mapped_fields: set[str],
) -> tuple[Decimal | None, int]:
    """汇总新增清单中购置类新增的原值合计；返回 (合计, 行数)。"""
    if "original_value" not in mapped_fields:
        return None, 0
    total = Decimal("0")
    count = 0
    saw_data_row = False
    for record in records:
        if record_is_empty_data_row(record, mapped_fields):
            continue
        saw_data_row = True
        if "addition_method" in mapped_fields and not is_purchase_addition_method(
            record.addition_method
        ):
            continue
        amount = parse_amount(record.original_value)
        if amount is None:
            continue
        total += amount
        count += 1
    if not saw_data_row:
        return None, 0
    return (total if count else Decimal("0")), count
