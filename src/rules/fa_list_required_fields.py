from __future__ import annotations

from ingest.constants import (
    FA_LIST_RECOMMENDED,
    FA_LIST_REQUIRED,
    FA_LIST_REQUIRED_IDENTITY,
)

from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, record_has_identity, record_is_empty_data_row

RULE_ID = "fa_list_required_fields"

_ROW_CORE = list(FA_LIST_REQUIRED)
_ROW_RECOMMENDED = list(FA_LIST_RECOMMENDED)


def _sheet_level_issues(ctx: ColumnContext) -> list[QcIssue]:
    present = ctx.mapped_fields
    issues: list[QcIssue] = []

    has_identity = (
        FA_LIST_REQUIRED_IDENTITY[0] in present
        or FA_LIST_REQUIRED_IDENTITY[1] in present
    )
    if not has_identity:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="asset_id|asset_name",
                severity=Severity.FAIL,
                message="FA list 缺少资产标识列（固定资产编号或资产名称）",
                suggestion="补充资产编号或资产名称列并完成字段映射",
                procedure_code=ctx.procedure_code,
                source_sheet=ctx.source_sheet,
            )
        )

    for field_name in FA_LIST_REQUIRED:
        if field_name not in present:
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=field_name,
                    severity=Severity.FAIL,
                    message=f"FA list 未映射核心列：{field_name}",
                    suggestion="在底稿或清单中补充该列，或扩展字段同义词映射",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                )
            )

    for field_name in FA_LIST_RECOMMENDED:
        if field_name not in present:
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=field_name,
                    severity=Severity.WARN,
                    message=f"FA list 未映射建议列：{field_name}",
                    suggestion="建议补充该列以支持折旧与分类分析",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                )
            )

    return issues


def _row_level_issues(
    record: AssetRecord,
    ctx: ColumnContext,
) -> list[QcIssue]:
    present = ctx.mapped_fields
    if record_is_empty_data_row(record, present):
        return []

    issues: list[QcIssue] = []
    aid = record.asset_id or record.identity()

    has_id_col = FA_LIST_REQUIRED_IDENTITY[0] in present
    has_name_col = FA_LIST_REQUIRED_IDENTITY[1] in present
    if (has_id_col or has_name_col) and not record_has_identity(record):
        issues.append(
            QcIssue(
                asset_id=aid,
                rule_id=RULE_ID,
                field="asset_id|asset_name",
                severity=Severity.FAIL,
                message="资产编号与资产名称均为空",
                suggestion="至少填写固定资产编号或资产名称",
                procedure_code=ctx.procedure_code,
                source_sheet=ctx.source_sheet,
                source_row=record.source_row,
            )
        )

    for field_name in _ROW_CORE:
        if field_name not in present:
            continue
        value = getattr(record, field_name, None)
        if is_blank(value):
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field=field_name,
                    severity=Severity.FAIL,
                    message=f"核心字段 {field_name} 为空",
                    suggestion="补充该字段后重新质检",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )

    for field_name in _ROW_RECOMMENDED:
        if field_name not in present:
            continue
        value = getattr(record, field_name, None)
        if is_blank(value):
            issues.append(
                QcIssue(
                    asset_id=aid,
                    rule_id=RULE_ID,
                    field=field_name,
                    severity=Severity.WARN,
                    message=f"建议字段 {field_name} 为空",
                    suggestion="建议补充该字段以便完整折旧与分类分析",
                    procedure_code=ctx.procedure_code,
                    source_sheet=ctx.source_sheet,
                    source_row=record.source_row,
                )
            )

    return issues


def check_fa_list_required_fields(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    issues = _sheet_level_issues(ctx)
    for record in records:
        issues.extend(_row_level_issues(record, ctx))
    return issues
