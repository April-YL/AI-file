from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity

RULE_ID = "asset_value_consistency"
DEFAULT_TOLERANCE = Decimal("0.01")


def _parse_amount(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def check_asset_value_consistency(
    records: list[AssetRecord],
    ctx: ColumnContext,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    amount_fields = ("original_value", "accumulated_depreciation", "net_value")
    required_mapped = all(f in ctx.mapped_fields for f in amount_fields)

    if not required_mapped:
        missing = [f for f in amount_fields if f not in ctx.mapped_fields]
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="original_value/net_value",
                severity=Severity.NEED_REVIEW,
                message=f"金额勾稽所需列未完整映射：{', '.join(missing)}",
                suggestion="补充原值、累计折旧、净值列映射后再执行金额关系校验",
                procedure_code=ctx.procedure_code,
                source_sheet=ctx.source_sheet,
            )
        )
        return issues

    for record in records:
        aid = record.asset_id or record.identity()
        original = _parse_amount(record.original_value)
        accumulated = _parse_amount(record.accumulated_depreciation)
        impairment = _parse_amount(record.impairment_provision)
        net = _parse_amount(record.net_value)

        if impairment is None:
            impairment = Decimal("0")

        if original is None or accumulated is None or net is None:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="original_value/net_value",
                    severity=Severity.NEED_REVIEW,
                    message="原值、累计折旧或净值无法解析为数值，无法自动勾稽",
                    suggestion="确认金额格式正确；含文字或公式时请人工复核",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )
            continue

        expected = original - accumulated - impairment
        diff = abs(expected - net)
        if diff > tolerance:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="net_value",
                    severity=Severity.FAIL,
                    message=(
                        f"净值与原值减累计折旧不一致："
                        f"净值={net}，计算值={expected}，差异={diff}"
                    ),
                    suggestion="核对原值、累计折旧、减值准备与净值口径",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )

    return issues
