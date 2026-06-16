from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from ingest.models import AssetRecord
from ingest.records import DisposalListSummary, FaListDataset
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import amount_tolerance, is_blank, parse_amount, record_has_identity, record_is_empty_data_row

RULE_IDS = (
    "disposal_required_fields",
    "disposal_list_net_value_recalculation",
    "disposal_method_classification",
    "disposal_other_reduction_over_tt",
)
_REQUIRED_FIELDS = (
    "asset_category",
    "asset_id",
    "asset_name",
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "disposal_date",
    "disposal_method",
)
_FIELD_LABELS = {
    "asset_category": "固定资产类别",
    "asset_id": "固定资产编号",
    "asset_name": "固定资产名称",
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧",
    "impairment_provision": "减值准备",
    "disposal_date": "处置日期",
    "disposal_method": "减少方式",
}


def run_disposal_list_rules(
    disposal_list: FaListDataset | None,
    disposal_list_summary: DisposalListSummary | None,
    *,
    lead: LeadSheetDataset | None = None,
) -> list[QcIssue]:
    if disposal_list is None:
        return []
    issues = check_disposal_required_fields(disposal_list)
    issues.extend(check_disposal_list_net_values(disposal_list))
    issues.extend(check_disposal_method_classification(disposal_list_summary))
    issues.extend(check_disposal_other_reduction_over_tt(disposal_list_summary, lead))
    return issues


def check_disposal_required_fields(disposal_list: FaListDataset) -> list[QcIssue]:
    issues: list[QcIssue] = []
    present = {mapping.standard_field for mapping in disposal_list.mapped_fields}
    for field_name in _REQUIRED_FIELDS:
        if field_name not in present:
            issues.append(
                _issue(
                    "disposal_required_fields",
                    field_name,
                    Severity.FAIL,
                    f"处置清单未映射必需列：{_FIELD_LABELS[field_name]}。",
                    "补充该列，或扩展字段同义词映射后重新质检；净值列可不提供。",
                    disposal_list.source_sheet,
                )
            )
    for record in disposal_list.records:
        if record_is_empty_data_row(record, present):
            continue
        asset_id = record.asset_id or record.identity()
        if not record_has_identity(record):
            issues.append(
                _issue(
                    "disposal_required_fields",
                    "asset_id|asset_name",
                    Severity.FAIL,
                    "处置清单行缺少资产编号和资产名称，无法识别单项处置资产。",
                    "补充资产编号和名称，或确认该行不是资产明细。",
                    disposal_list.source_sheet,
                    record.source_row,
                    asset_id,
                )
            )
        for field_name in _REQUIRED_FIELDS:
            if field_name in present and is_blank(getattr(record, field_name, None)):
                issues.append(
                    _issue(
                        "disposal_required_fields",
                        field_name,
                        Severity.FAIL,
                        f"处置清单必需字段 {_FIELD_LABELS[field_name]} 为空。",
                        "补充该字段后重新质检；净值由原值、累计折旧和减值准备重算。",
                        disposal_list.source_sheet,
                        record.source_row,
                        asset_id,
                    )
                )
    return issues


def check_disposal_list_net_values(disposal_list: FaListDataset) -> list[QcIssue]:
    present = {mapping.standard_field for mapping in disposal_list.mapped_fields}
    required = {"original_value", "accumulated_depreciation", "impairment_provision"}
    if not required.issubset(present) or "net_value" not in present:
        return []
    issues: list[QcIssue] = []
    for record in disposal_list.records:
        if record_is_empty_data_row(record, present):
            continue
        original = parse_amount(record.original_value)
        accumulated = parse_amount(record.accumulated_depreciation)
        impairment = parse_amount(record.impairment_provision)
        net = parse_amount(record.net_value)
        if None in {original, accumulated, impairment, net}:
            continue
        expected = original - abs(accumulated) - abs(impairment)
        diff = abs(net - expected)
        if diff <= amount_tolerance(max(abs(net), abs(expected))):
            continue
        issues.append(
            _issue(
                "disposal_list_net_value_recalculation",
                "net_value",
                Severity.FAIL,
                f"处置清单净值计算不成立：记录净值={net}，按原值-累计折旧-减值准备计算={expected}。",
                "核对处置清单原值、累计折旧、减值准备及净值。",
                disposal_list.source_sheet,
                record.source_row,
                record.asset_id or record.identity(),
            )
        )
    return issues


def check_disposal_method_classification(
    summary: DisposalListSummary | None,
) -> list[QcIssue]:
    if summary is None:
        return []
    bucket = next((item for item in summary.buckets if item.bucket_key == "unknown"), None)
    if bucket is None or bucket.record_count == 0:
        return []
    return [
        _issue(
            "disposal_method_classification",
            "disposal_method",
            Severity.NEED_REVIEW,
            f"处置清单有 {bucket.record_count} 条减少方式未能分类，净值合计={bucket.net_value_total}。",
            "确认这些项目属于出售、报废还是其他减少；未分类金额不得直接纳入处置测试总体。",
            summary.source_sheet,
            bucket.source_rows[0] if bucket.source_rows else None,
        )
    ]


def check_disposal_other_reduction_over_tt(
    summary: DisposalListSummary | None,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    if summary is None:
        return []
    other = parse_amount(summary.other_reduction_net_value) or Decimal("0")
    if other == 0:
        return []
    tt = _lead_threshold(lead, "tt")
    if tt is not None and abs(other) <= tt:
        return []
    threshold_text = f"超过 TT（{tt}）" if tt is not None else "未读取到 TT，无法判断是否超过测试阈值"
    return [
        _issue(
            "disposal_other_reduction_over_tt",
            "disposal_method",
            Severity.NEED_REVIEW,
            f"处置清单存在其他减少净值={other}，{threshold_text}。",
            "其他减少与出售/报废性质不同，请确认是否需要单独总体及其他审计程序。",
            summary.source_sheet,
        )
    ]


def _lead_threshold(lead: LeadSheetDataset | None, key: str) -> Decimal | None:
    if lead is None:
        return None
    amount = parse_amount(field_values(lead).get(key))
    return amount if amount is not None and amount > 0 else None


def _issue(
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    source_sheet: str,
    source_row: int | None = None,
    asset_id: str | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=asset_id,
        rule_id=rule_id,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.02.2",
        source_sheet=source_sheet,
        source_row=source_row,
    )
