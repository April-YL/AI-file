from __future__ import annotations

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, parse_amount, record_is_empty_data_row

RULE_ID = "asset_amount_non_negative"

_AMOUNT_FIELDS = (
    ("original_value", "原值"),
    ("net_value", "净值"),
)

_CONTRA_FIELDS = ("accumulated_depreciation", "impairment_provision")


def check_asset_amount_non_negative(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    mapped = ctx.mapped_fields

    check_fields = [
        (f, label) for f, label in _AMOUNT_FIELDS if f in mapped
    ]
    if not check_fields and not any(field in mapped for field in _CONTRA_FIELDS):
        return issues

    for record in records:
        if record_is_empty_data_row(record, mapped):
            continue
        aid = record.asset_id or record.identity()

        for field_name, label in check_fields:
            raw = getattr(record, field_name, None)
            if is_blank(raw):
                continue
            amount = parse_amount(raw)
            if amount is None:
                continue
            if amount < 0:
                issues.append(
                    QcIssue(
                        asset_id=aid,
                        rule_id=RULE_ID,
                        field=field_name,
                        severity=Severity.FAIL,
                        message=f"{label}为负数（{raw}）",
                        suggestion="核对底稿金额符号与口径，修正负值或说明调整事项",
                        procedure_code=ctx.procedure_code,
                        source_sheet=ctx.source_sheet,
                        source_row=record.source_row,
                    )
                )

    mixed_fields: list[str] = []
    for field_name in _CONTRA_FIELDS:
        if field_name not in mapped:
            continue
        signs: set[int] = set()
        for record in records:
            raw = getattr(record, field_name, None)
            if is_blank(raw):
                continue
            amount = parse_amount(raw)
            if amount is None or amount == 0:
                continue
            signs.add(1 if amount > 0 else -1)
        if len(signs) > 1:
            mixed_fields.append(field_name)
    if mixed_fields:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="|".join(mixed_fields),
                severity=Severity.NEED_REVIEW,
                message="累计折旧或减值准备列存在正负号口径混用",
                suggestion="确认抵减金额的借贷方向；统一口径后再复核净值关系",
                procedure_code=ctx.procedure_code,
                source_sheet=ctx.source_sheet,
            )
        )

    return issues
