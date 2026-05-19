from __future__ import annotations

from decimal import Decimal

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, parse_amount, record_is_empty_data_row

RULE_ID = "salvage_rate_range"


def _parse_rate(value: str) -> tuple[Decimal | None, bool]:
    """返回 (比率 0-1, 是否按百分比输入)。"""
    text = str(value).strip().replace("%", "")
    amount = parse_amount(text)
    if amount is None:
        return None, False
    if amount > 1:
        return amount / Decimal("100"), True
    return amount, False


def check_salvage_rate_range(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    if "salvage_rate" not in ctx.mapped_fields:
        return issues

    for record in records:
        if record_is_empty_data_row(record, ctx.mapped_fields):
            continue
        raw = record.salvage_rate
        if is_blank(raw):
            continue
        aid = record.asset_id or record.identity()
        rate, was_percent = _parse_rate(raw)
        if rate is None:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="salvage_rate",
                    severity=Severity.NEED_REVIEW,
                    message=f"残值率「{raw}」无法解析",
                    suggestion="请使用 0-1 小数或带 % 的百分比",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )
            continue
        if rate < 0 or rate > 1:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="salvage_rate",
                    severity=Severity.FAIL,
                    message=f"残值率应在 0 到 1 之间，当前为 {raw}",
                    suggestion="核对残值率口径（比例而非金额）",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )
        elif was_percent and rate <= 1:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="salvage_rate",
                    severity=Severity.WARN,
                    message=f"残值率「{raw}」已按百分比换算为 {rate}",
                    suggestion="确认与客户台账口径一致（小数 vs 百分比）",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )

    return issues
