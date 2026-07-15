from __future__ import annotations

from decimal import Decimal

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import (
    amount_tolerance,
    is_blank,
    parse_amount,
    record_is_empty_data_row,
)

RULE_ID = "asset_value_consistency"


def check_asset_value_consistency(
    records: list[AssetRecord],
    ctx: ColumnContext,
    tolerance: Decimal | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    amount_fields = (
        "original_value",
        "accumulated_depreciation",
        "impairment_provision",
        "net_value",
    )
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
        if record_is_empty_data_row(record, ctx.mapped_fields):
            continue

        aid = record.asset_id or record.identity()
        original = parse_amount(record.original_value)
        accumulated = parse_amount(record.accumulated_depreciation)
        impairment_raw = record.impairment_provision
        impairment = parse_amount(impairment_raw)
        net = parse_amount(record.net_value)

        if is_blank(impairment_raw):
            impairment = Decimal("0")

        if original is None and accumulated is None and net is None:
            continue

        if original is None or accumulated is None or impairment is None or net is None:
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

        # 客户台账常按贷方负数列示累计折旧/减值；金额关系按抵减金额绝对值勾稽。
        expected = original - abs(accumulated) - abs(impairment)
        diff = abs(expected - net)
        tol = tolerance if tolerance is not None else amount_tolerance(original)
        if diff > tol:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="net_value",
                    severity=Severity.FAIL,
                    message=(
                        f"净值与原值减累计折旧不一致："
                        f"净值={net}，计算值={expected}，差异={diff}（允差={tol}）"
                    ),
                    suggestion="核对原值、累计折旧、减值准备与净值口径",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )

    return issues
