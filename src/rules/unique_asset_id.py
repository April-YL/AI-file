from __future__ import annotations

from collections import defaultdict

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity

RULE_ID = "unique_asset_id"


def check_unique_asset_id(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    issues: list[QcIssue] = []

    if "asset_id" not in ctx.mapped_fields:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="asset_id",
                severity=Severity.NEED_REVIEW,
                message="未映射固定资产编号列，无法自动校验编号唯一性",
                suggestion="补充资产编号列；若仅有名称，请人工核对是否重复",
                procedure_code=ctx.procedure_code,
                source_sheet=ctx.source_sheet,
            )
        )
        return issues

    by_id: dict[str, list[AssetRecord]] = defaultdict(list)
    for record in records:
        if record.asset_id is None or not str(record.asset_id).strip():
            continue
        key = str(record.asset_id).strip()
        by_id[key].append(record)

    for asset_id, group in by_id.items():
        if len(group) < 2:
            continue
        for record in group:
            issues.append(
                QcIssue(
                    asset_id=asset_id,
                    rule_id=RULE_ID,
                    field="asset_id",
                    severity=Severity.FAIL,
                    message=f"固定资产编号 {asset_id} 重复出现 {len(group)} 次",
                    suggestion="核对台账来源并修正重复编号",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )

    return issues
