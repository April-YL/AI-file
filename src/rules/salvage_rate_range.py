from __future__ import annotations

from decimal import Decimal

from ingest.models import AssetRecord, FaListSalvageBasis, FaListSalvageMode
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, parse_amount, record_is_empty_data_row

RULE_ID = "salvage_rate_range"
_RATE_CROSSCHECK_TOLERANCE = Decimal("0.0001")


def _parse_rate(value: str, *, percent_scale: bool) -> Decimal | None:
    text_value = str(value).strip()
    text = text_value.replace("%", "")
    amount = parse_amount(text)
    if amount is None:
        return None
    if "%" in text_value or percent_scale:
        return amount / Decimal("100") if abs(amount) > 1 else amount
    return amount


def check_salvage_rate_range(
    records: list[AssetRecord],
    ctx: ColumnContext,
    salvage_basis: FaListSalvageBasis | None = None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    crosscheck_mismatch_count = 0
    crosscheck_representative: tuple[AssetRecord, Decimal, Decimal] | None = None
    mode = salvage_basis.mode if salvage_basis else FaListSalvageMode.EXPLICIT_RATE
    if mode in {FaListSalvageMode.UNRESOLVED, FaListSalvageMode.MISSING}:
        return issues
    use_value = mode == FaListSalvageMode.DERIVED_FROM_VALUE
    header = ctx.mapped_headers.get("salvage_rate", "")
    percent_scale = "%" in header or "百分比" in header

    for record in records:
        if record_is_empty_data_row(record, ctx.mapped_fields):
            continue
        raw = record.salvage_value if use_value else record.salvage_rate
        if is_blank(raw):
            continue
        aid = record.asset_id or record.identity()
        if use_value:
            salvage_value = parse_amount(raw)
            original = parse_amount(record.original_value)
            rate = (
                salvage_value / original
                if salvage_value is not None and original not in (None, Decimal("0"))
                else None
            )
        else:
            rate = _parse_rate(raw, percent_scale=percent_scale)
        if rate is None:
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="salvage_value" if use_value else "salvage_rate",
                    severity=Severity.NEED_REVIEW,
                    message=f"残值率「{raw}」无法解析",
                    suggestion="请使用 0-1 小数或带 % 的百分比",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )
            continue
        if mode == FaListSalvageMode.RATE_AND_VALUE:
            salvage_value = parse_amount(record.salvage_value)
            original = parse_amount(record.original_value)
            derived_rate = (
                salvage_value / original
                if salvage_value is not None and original not in (None, Decimal("0"))
                else None
            )
            if (
                derived_rate is not None
                and abs(derived_rate - rate) > _RATE_CROSSCHECK_TOLERANCE
            ):
                crosscheck_mismatch_count += 1
                if crosscheck_representative is None:
                    crosscheck_representative = (record, rate, derived_rate)
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

    if crosscheck_representative is not None:
        record, explicit_rate, derived_rate = crosscheck_representative
        issues.append(
            QcIssue(
                asset_id=record.asset_id or record.identity(),
                rule_id=RULE_ID,
                field="salvage_rate",
                severity=Severity.NEED_REVIEW,
                message=(
                    f"残值率与残值金额/原值换算口径不一致，共 {crosscheck_mismatch_count} 行；"
                    f"代表行显式残值率为 {explicit_rate}，换算残值率为 {derived_rate}"
                ),
                suggestion="核对残值率、残值金额和原值是否属于同一期间及同一金额口径",
                procedure_code=ctx.procedure_code,
                source_sheet=ctx.source_sheet,
                source_row=record.source_row,
            )
        )

    return issues
