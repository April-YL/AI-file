from __future__ import annotations

import re
from decimal import Decimal

from ingest.lead_sheet import CraAssertionRow, LeadSheetDataset
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.parsing import amount_tolerance, is_blank, parse_amount

# 与 docs/planning/lead-qc-rules.md GAM 资产/收入账户区间一致（占 TE 比例）
GAM_TT_RATIO_BANDS: dict[str, tuple[Decimal, Decimal]] = {
    "lowest": (Decimal("0.75"), Decimal("1.00")),
    "low": (Decimal("0.50"), Decimal("0.75")),
    "moderate": (Decimal("0.25"), Decimal("0.50")),
    "high": (Decimal("0.10"), Decimal("0.25")),
}

_CRA_TIER_ALIASES: dict[str, str] = {
    "minimal": "lowest",
    "lowest": "lowest",
    "最低": "lowest",
    "low": "low",
    "低": "low",
    "moderate": "moderate",
    "medium": "moderate",
    "中等": "moderate",
    "high": "high",
    "高": "high",
}

_MOVEMENT_LABEL_TO_FIELD: dict[str, str] = {
    "原值": "original_value",
    "累计折旧": "accumulated_depreciation",
    "减值准备": "impairment_provision",
    "净值": "net_value",
}

_REQUIRED_MOVEMENT_LABELS = ("原值", "累计折旧", "减值准备", "净值")

_TRIVIAL_FLUCTUATION_PHRASES = (
    "无异常波动",
    "无异常",
    "无波动",
    "不适用",
    "n/a",
    "na",
)


def field_values(lead: LeadSheetDataset) -> dict[str, str | None]:
    by_key = {f.field_key: f.value for f in lead.basic_info_fields}
    for cap in lead.materiality:
        if cap.field_key in ("te", "sad", "pm"):
            if cap.workpaper_value and not is_blank(cap.workpaper_value):
                by_key.setdefault(cap.field_key, cap.workpaper_value)
    return by_key


def skip_cra_module(lead: LeadSheetDataset) -> bool:
    return lead.layout_variant == "no_cra_te_volatility"


def parse_threshold_amount(value: str | None) -> Decimal | None:
    return parse_amount(value)


def cra_tier(cra: str | None) -> str | None:
    if is_blank(cra):
        return None
    key = re.sub(r"[\s_\-（）()]", "", str(cra).strip().lower())
    if key in _CRA_TIER_ALIASES:
        return _CRA_TIER_ALIASES[key]
    for alias, tier in _CRA_TIER_ALIASES.items():
        if alias in key or key in alias:
            return tier
    return None


def assertion_tt_values(cra_rows: list[CraAssertionRow]) -> list[Decimal]:
    out: list[Decimal] = []
    for row in cra_rows:
        amt = parse_threshold_amount(row.tt)
        if amt is not None and amt > 0:
            out.append(amt)
    return out


def overall_tt_value(cra_rows: list[CraAssertionRow]) -> Decimal | None:
    for row in cra_rows:
        amt = parse_threshold_amount(row.tt_overall)
        if amt is not None:
            return amt
    return None


def effective_overall_threshold(cra_rows: list[CraAssertionRow]) -> Decimal | None:
    """整体 TT：优先「所有相关认定」列，否则取认定 TT 最小值（排除 0）。"""
    overall = overall_tt_value(cra_rows)
    if overall is not None:
        return overall
    tts = assertion_tt_values(cra_rows)
    return min(tts) if tts else None


def amounts_close(a: Decimal, b: Decimal, *, ref: Decimal | None = None) -> bool:
    base = ref if ref is not None else max(abs(a), abs(b), Decimal("1"))
    return abs(a - b) <= amount_tolerance(base)


def is_affirmative(value: str | None) -> bool:
    if is_blank(value):
        return False
    n = re.sub(r"[\s_\-]", "", str(value).strip().lower())
    return n in ("是", "yes", "y", "true", "1", "需", "需要", "有")


def is_trivial_fluctuation_note(text: str | None) -> bool:
    if is_blank(text):
        return True
    n = re.sub(r"[\s_\-]", "", str(text).strip().lower())
    return any(p in n for p in _TRIVIAL_FLUCTUATION_PHRASES)


def movement_field_key(account_label: str) -> str | None:
    n = re.sub(r"[\s_\-]", "", account_label)
    for label, key in _MOVEMENT_LABEL_TO_FIELD.items():
        if label in account_label or label.replace(" ", "") in n:
            return key
    return None


def movement_amount_for_row(values: dict[str, str | None]) -> Decimal | None:
    explicit = parse_threshold_amount(values.get("movement_amount"))
    if explicit is not None:
        return explicit
    ending = parse_threshold_amount(values.get("audited_ending"))
    opening = parse_threshold_amount(values.get("py_audited"))
    if ending is not None and opening is not None:
        return ending - opening
    return None


def lead_book_balance(values: dict[str, str | None]) -> Decimal | None:
    for role in ("book_balance", "audited_ending", "unaudited"):
        amt = parse_threshold_amount(values.get(role))
        if amt is not None:
            return amt
    return None
