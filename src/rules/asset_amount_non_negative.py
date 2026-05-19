from __future__ import annotations

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, parse_amount, record_is_empty_data_row

RULE_ID = "asset_amount_non_negative"

_AMOUNT_FIELDS = (
    ("original_value", "原值"),
    ("accumulated_depreciation", "累计折旧"),
    ("impairment_provision", "减值准备"),
    ("net_value", "净值"),
)


def check_asset_amount_non_negative(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    mapped = ctx.mapped_fields

    check_fields = [
        (f, label) for f, label in _AMOUNT_FIELDS if f in mapped
    ]
    if not check_fields:
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

    return issues
