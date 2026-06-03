from __future__ import annotations

from decimal import Decimal

from ingest.models import AssetRecord
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount, record_is_empty_data_row
from rules.rollforward_common import rollforward_sheet_parseable

RULE_ID = "rollforward_abnormal_amounts"

_AMOUNT_TOL = Decimal("0.01")


def _issue(
    *,
    rollforward: RollforwardSheetDataset,
    field: str,
    message: str,
    suggestion: str,
    source_row: int | None = None,
    severity: Severity = Severity.FAIL,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=RULE_ID,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.01",
        source_sheet=rollforward.source_sheet,
        source_row=source_row,
    )


def _check_amount_set(
    rollforward: RollforwardSheetDataset,
    *,
    label: str,
    original: Decimal | None,
    accumulated: Decimal | None,
    impairment: Decimal | None,
    net: Decimal | None,
    source_row: int | None,
) -> list[QcIssue]:
    if original is None and accumulated is None and net is None:
        return []

    issues: list[QcIssue] = []
    imp = impairment if impairment is not None else Decimal("0")

    if original is not None and accumulated is not None:
        if accumulated > original + _AMOUNT_TOL:
            issues.append(
                _issue(
                    rollforward=rollforward,
                    field="accumulated_depreciation/original_value",
                    message=(
                        f"{label}：累计折旧（{accumulated}）大于原值（{original}），"
                        "可能存在后推填列或分类错误"
                    ),
                    suggestion="核对 SOP【01】易错点：处置转出、累折与原值关系",
                    source_row=source_row,
                )
            )
        if imp > original + _AMOUNT_TOL:
            issues.append(
                _issue(
                    rollforward=rollforward,
                    field="impairment_provision/original_value",
                    message=f"{label}：减值准备（{imp}）大于原值（{original}）",
                    suggestion="核对减值与原值口径及后推填列",
                    source_row=source_row,
                )
            )
        if imp + accumulated > original + _AMOUNT_TOL:
            issues.append(
                _issue(
                    rollforward=rollforward,
                    field="accumulated_depreciation/impairment_provision",
                    message=(
                        f"{label}：累计折旧+减值（{accumulated + imp}）大于原值（{original}），"
                        "符合处置转出勾稽异常特征"
                    ),
                    suggestion="核对处置/报废行的转出原值、累计折旧与减值准备",
                    source_row=source_row,
                )
            )

    if net is not None and net < -_AMOUNT_TOL:
        issues.append(
            _issue(
                rollforward=rollforward,
                field="net_value",
                message=f"{label}：净值为负（{net}）",
                suggestion="核对后推表净值计算及四口径勾稽",
                source_row=source_row,
            )
        )

    if original is not None and original < -_AMOUNT_TOL and label.endswith("合计"):
        issues.append(
            _issue(
                rollforward=rollforward,
                field="original_value",
                message=f"{label}：原值合计为负（{original}）",
                suggestion="合计行原值通常应为非负；请核对是否误取变动行或符号口径",
                source_row=source_row,
            )
        )

    return issues


def _check_detail_record(
    rollforward: RollforwardSheetDataset,
    record: AssetRecord,
) -> list[QcIssue]:
    b1 = rollforward.section_regions.get("b1_bkd_main_table")
    if b1 and b1.start_row and b1.end_row and record.source_row:
        if record.source_row < b1.start_row or record.source_row > b1.end_row:
            return []

    mapped = {m.standard_field for m in rollforward.mapped_fields}
    if not mapped:
        mapped = {"original_value", "accumulated_depreciation", "net_value"}
    if record_is_empty_data_row(record, mapped):
        return []

    original = parse_amount(record.original_value)
    accumulated = parse_amount(record.accumulated_depreciation)
    impairment = parse_amount(record.impairment_provision)
    net = parse_amount(record.net_value)
    if original is None and accumulated is None and net is None:
        return []

    label = f"明细行（行{record.source_row or '?'}）"
    return _check_amount_set(
        rollforward,
        label=label,
        original=original,
        accumulated=accumulated,
        impairment=impairment,
        net=net,
        source_row=record.source_row,
    )


def check_rollforward_abnormal_amounts(
    rollforward: RollforwardSheetDataset | None,
) -> list[QcIssue]:
    """K.01 后推表异常金额（累折>原值、负净值、转出勾稽异常）。"""
    if rollforward is None or not rollforward.source_sheet:
        return []
    if not rollforward_sheet_parseable(rollforward):
        return []

    issues: list[QcIssue] = []
    issues.extend(
        _check_amount_set(
            rollforward,
            label="期初合计",
            original=rollforward.opening_totals.get("original_value"),
            accumulated=rollforward.opening_totals.get("accumulated_depreciation"),
            impairment=rollforward.opening_totals.get("impairment_provision"),
            net=rollforward.opening_totals.get("net_value"),
            source_row=rollforward.total_row,
        )
    )
    issues.extend(
        _check_amount_set(
            rollforward,
            label="期末合计",
            original=rollforward.ending_totals.get("original_value"),
            accumulated=rollforward.ending_totals.get("accumulated_depreciation"),
            impairment=rollforward.ending_totals.get("impairment_provision"),
            net=rollforward.ending_totals.get("net_value"),
            source_row=rollforward.total_row,
        )
    )

    for record in rollforward.detail_records:
        issues.extend(_check_detail_record(rollforward, record))

    return issues
