from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from ingest.models import AmountGroupStatus, AssetRecord
from ingest.records import DisposalListSummary, FaListDataset
from rules.execution_recorder import RuleExecutionRecorder
from rules.lead_common import lead_tt
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
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    if disposal_list is None:
        for rule_id in RULE_IDS:
            recorder.record_data_insufficient(rule_id, "未识别处置清单，无法执行处置清单相关检查")
        return []
    issues = recorder.execute_rule("disposal_required_fields", check_disposal_required_fields, disposal_list)
    issues.extend(recorder.execute_rule("disposal_list_net_value_recalculation", check_disposal_list_net_values, disposal_list))
    issues.extend(recorder.execute_rule("disposal_method_classification", check_disposal_method_classification, disposal_list_summary))
    issues.extend(recorder.execute_rule("disposal_other_reduction_over_tt", check_disposal_other_reduction_over_tt, disposal_list_summary, lead))
    return issues

def check_disposal_required_fields(disposal_list: FaListDataset) -> list[QcIssue]:
    issues: list[QcIssue] = []
    present = {mapping.standard_field for mapping in disposal_list.mapped_fields}
    amount_group = _selected_amount_group(disposal_list)
    for field_name in _REQUIRED_FIELDS:
        if field_name not in present:
            ambiguous_amount_field = (
                field_name in {"original_value", "accumulated_depreciation", "impairment_provision", "net_value"}
                and amount_group is not None
                and amount_group.status != AmountGroupStatus.CONFIRMED
            )
            issues.append(
                _issue(
                    "disposal_required_fields",
                    field_name,
                    Severity.NEED_REVIEW if ambiguous_amount_field else Severity.FAIL,
                    (
                        f"处置清单金额字段组不完整，无法确认同口径的{_FIELD_LABELS[field_name]}。"
                        if ambiguous_amount_field
                        else f"处置清单未映射必需列：{_FIELD_LABELS[field_name]}。"
                    ),
                    (
                        "请确认原值、累计折旧、减值准备和净值是否属于同一期间、币种及处置口径。"
                        if ambiguous_amount_field
                        else "补充该列，或扩展字段同义词映射后重新质检；净值列可不提供。"
                    ),
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
    amount_group = _selected_amount_group(disposal_list)
    if amount_group is not None and amount_group.status != AmountGroupStatus.CONFIRMED:
        dimensions = (
            f"期间={amount_group.period_role.value}、币种={amount_group.currency_role.value}、"
            f"业务角色={amount_group.business_role.value}"
        )
        missing = "、".join(amount_group.missing_measures) or "存在多个候选金额组"
        return [
            _issue(
                "disposal_list_net_value_recalculation",
                "amount_group",
                Severity.NEED_REVIEW,
                f"处置清单金额组无法支持确定性净值重算：{dimensions}；缺失/冲突={missing}。",
                "请人工确认同一期间、同一币种、同一处置口径的原值、累计折旧、减值准备和净值列。",
                disposal_list.source_sheet,
            )
        ]
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


def _selected_amount_group(disposal_list: FaListDataset):
    selected_id = disposal_list.selected_amount_group_id
    return next(
        (group for group in disposal_list.amount_groups if group.group_id == selected_id),
        None,
    )


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
    if summary.amount_group_status not in {None, AmountGroupStatus.CONFIRMED}:
        return [
            _issue(
                "disposal_other_reduction_over_tt",
                "amount_group",
                Severity.NEED_REVIEW,
                "处置清单金额组尚未确认，不能据其汇总金额判断其他减少是否超过 TT。",
                "先确认同期间、同币种、同处置口径的完整金额组，再执行阈值比较。",
                summary.source_sheet,
            )
        ]
    other = parse_amount(summary.other_reduction_net_value) or Decimal("0")
    if other == 0:
        return []
    tt = lead_tt(lead)
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
