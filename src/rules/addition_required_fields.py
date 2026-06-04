from __future__ import annotations

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, record_has_identity, record_is_empty_data_row

RULE_ID = "addition_required_fields"

_REQUIRED_FIELDS = (
    "asset_category",
    "asset_id",
    "asset_name",
    "start_date",
    "original_value",
    "addition_method",
)

_FIELD_LABELS = {
    "asset_category": "固定资产类别",
    "asset_id": "固定资产编号",
    "asset_name": "固定资产名称",
    "start_date": "入账开始日期",
    "original_value": "原值",
    "addition_method": "新增方式",
}


def check_addition_required_fields(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    """新增清单必需字段完整性检查。"""
    issues: list[QcIssue] = []
    present = ctx.mapped_fields

    for field_name in _REQUIRED_FIELDS:
        if field_name not in present:
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=field_name,
                    severity=Severity.FAIL,
                    message=f"新增清单未映射必需列：{_FIELD_LABELS[field_name]}",
                    suggestion="补充该列，或扩展字段同义词映射后重新质检。",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                )
            )

    for record in records:
        if record_is_empty_data_row(record, present):
            continue
        aid = record.asset_id or record.identity()
        if not record_has_identity(record):
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field="asset_id|asset_name",
                    severity=Severity.FAIL,
                    message="新增清单行缺少资产编号和资产名称，无法识别单项新增资产。",
                    suggestion="补充固定资产编号和固定资产名称，或确认该行不是资产明细。",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )
        for field_name in _REQUIRED_FIELDS:
            if field_name not in present:
                continue
            if is_blank(getattr(record, field_name, None)):
                issues.append(
                    QcIssue(
                        asset_id=aid,
                        rule_id=RULE_ID,
                        field=field_name,
                        severity=Severity.FAIL,
                        message=f"新增清单必需字段 {_FIELD_LABELS[field_name]} 为空。",
                        suggestion="补充该字段后重新质检；若该行不是资产明细，请从清单中剔除或标明。",
                        procedure_code=ctx.procedure_code,
                        source_sheet=ctx.source_sheet,
                        source_row=record.source_row,
                    )
                )

    return issues
