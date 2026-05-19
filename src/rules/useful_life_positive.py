from __future__ import annotations

import re

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, record_is_empty_data_row

RULE_ID = "useful_life_positive"

_YEAR_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*年")


def _parse_months(value: str) -> int | None:
    text = str(value).strip()
    if not text:
        return None
    year_match = _YEAR_PATTERN.search(text)
    if year_match and "月" not in text:
        years = float(year_match.group(1))
        return int(years * 12) if years > 0 else None
    digits = re.sub(r"[^\d.]", "", text)
    if not digits:
        return None
    try:
        months = float(digits)
    except ValueError:
        return None
    if "年" in text and "月" not in text:
        return int(months * 12)
    return int(months) if months == int(months) else int(round(months))


def check_useful_life_positive(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    if "useful_life_months" not in ctx.mapped_fields:
        return issues

    for record in records:
        if record_is_empty_data_row(record, ctx.mapped_fields):
            continue
        raw = record.useful_life_months
        if is_blank(raw):
            continue
        aid = record.asset_id or record.identity()
        months = _parse_months(raw)
        if months is None:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="useful_life_months",
                    severity=Severity.NEED_REVIEW,
                    message=f"使用寿命「{raw}」无法解析为月数",
                    suggestion="请使用月数或「N年」格式，或由人工确认",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )
            continue
        if months <= 0:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="useful_life_months",
                    severity=Severity.FAIL,
                    message=f"使用寿命应为正数，当前为 {raw}",
                    suggestion="核对折旧年限/使用寿命列",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )

    return issues
