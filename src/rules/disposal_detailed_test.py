from __future__ import annotations

from decimal import Decimal

from ingest.disposal_test_sheet import DisposalTestSheetDataset, DisposalTestedSampleRow
from rules.execution_recorder import RuleExecutionRecorder
from rules.models import QcIssue, Severity
from rules.parsing import amount_tolerance, parse_amount

RULE_IDS = (
    "disposal_test_attributes_complete",
    "disposal_test_amount_recalculation",
    "disposal_sale_evidence_complete",
    "disposal_exception_followup",
)


def run_disposal_detailed_test_rules(
    disposal_test: DisposalTestSheetDataset | None,
    *,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    if disposal_test is None:
        for rule_id in RULE_IDS:
            recorder.record_data_insufficient(rule_id, "未识别 K.02.2 处置测试表，无法执行处置样本详细测试")
        return []
    issues: list[QcIssue] = []
    if not disposal_test.tested_samples:
        for rule_id in RULE_IDS:
            recorder.record_data_insufficient(rule_id, "未读取到处置测试样本，无法执行处置样本详细测试")
        return issues
    for sample in disposal_test.tested_samples:
        issues.extend(recorder.execute_rule("disposal_test_attributes_complete", _check_attributes, disposal_test, sample))
        issues.extend(recorder.execute_rule("disposal_test_amount_recalculation", _check_amounts, disposal_test, sample))
        issues.extend(recorder.execute_rule("disposal_sale_evidence_complete", _check_sale_evidence, disposal_test, sample))
        issues.extend(recorder.execute_rule("disposal_exception_followup", _check_exception_followup, disposal_test, sample))
    return issues

def _check_attributes(test: DisposalTestSheetDataset, sample: DisposalTestedSampleRow) -> list[QcIssue]:
    values = [str(value).strip() for value in sample.attribute_results if value not in (None, "")]
    if len(values) >= 3:
        return []
    return [
        _issue(
            "disposal_test_attributes_complete",
            "attribute_results",
            Severity.FAIL,
            f"K.02.2 处置样本未完整填写三个固定测试属性：{_identity(sample)}。",
            "完成资产正确转出、处置损益重算及适用时处置收入核对三个测试属性。",
            test.source_sheet,
            sample.source_row,
        )
    ]


def _check_amounts(test: DisposalTestSheetDataset, sample: DisposalTestedSampleRow) -> list[QcIssue]:
    issues: list[QcIssue] = []
    original = parse_amount(sample.original_value)
    accumulated = parse_amount(sample.accumulated_depreciation)
    impairment = parse_amount(sample.impairment_provision)
    net = parse_amount(sample.net_value)
    if None not in {original, accumulated, impairment, net}:
        expected_net = original - abs(accumulated) - abs(impairment)
        if abs(net - expected_net) > amount_tolerance(max(abs(net), abs(expected_net), Decimal("1"))):
            issues.append(
                _issue(
                    "disposal_test_amount_recalculation",
                    "net_value",
                    Severity.FAIL,
                    f"K.02.2 样本净值计算不成立：{_identity(sample)}，记录净值={net}，重算={expected_net}。",
                    "核对样本原值、累计折旧、减值准备和净值。",
                    test.source_sheet,
                    sample.source_row,
                )
            )
    sale = parse_amount(sample.sale_price)
    gain_loss = parse_amount(sample.disposal_gain_loss)
    if sale is not None and net is not None and gain_loss is not None:
        expected_gain_loss = sale - net
        if abs(gain_loss - expected_gain_loss) > amount_tolerance(max(abs(gain_loss), abs(expected_gain_loss), Decimal("1"))):
            issues.append(
                _issue(
                    "disposal_test_amount_recalculation",
                    "disposal_gain_loss",
                    Severity.FAIL,
                    f"K.02.2 样本处置损益计算不成立：{_identity(sample)}，记录处置损益={gain_loss}，重算={expected_gain_loss}。",
                    "核对出售价格、净值和处置损益。",
                    test.source_sheet,
                    sample.source_row,
                )
            )
    support = parse_amount(sample.support_sale_price or sample.evidence_amount)
    difference = parse_amount(sample.sale_price_difference or sample.amount_difference)
    if sale is not None and support is not None and difference is not None:
        expected_difference = support - sale
        if abs(difference - expected_difference) > amount_tolerance(max(abs(difference), abs(expected_difference), Decimal("1"))):
            issues.append(
                _issue(
                    "disposal_test_amount_recalculation",
                    "sale_price_difference",
                    Severity.FAIL,
                    f"K.02.2 样本出售价格差异计算不成立：{_identity(sample)}，记录差异={difference}，重算={expected_difference}。",
                    "核对账面出售价格、审计证据金额和差异公式。",
                    test.source_sheet,
                    sample.source_row,
                )
            )
    return issues


def _check_sale_evidence(test: DisposalTestSheetDataset, sample: DisposalTestedSampleRow) -> list[QcIssue]:
    is_sale = parse_amount(sample.sale_price) not in {None, Decimal("0")} or "出售" in str(sample.disposal_method or "")
    if not is_sale:
        return []
    missing: list[str] = []
    if parse_amount(sample.support_sale_price or sample.evidence_amount) is None:
        missing.append("审计证据取得的出售价格")
    if not sample.evidence_description:
        missing.append("支持性证据描述")
    if not missing:
        return []
    return [
        _issue(
            "disposal_sale_evidence_complete",
            "evidence",
            Severity.FAIL,
            f"K.02.2 出售样本缺少{'、'.join(missing)}：{_identity(sample)}。",
            "补充出售合同、发票、收款证明等支持性证据及对应金额。",
            test.source_sheet,
            sample.source_row,
        )
    ]


def _check_exception_followup(test: DisposalTestSheetDataset, sample: DisposalTestedSampleRow) -> list[QcIssue]:
    has_n = any(str(value).strip().upper() in {"N", "否", "NO"} for value in sample.attribute_results if value is not None)
    differences = [
        parse_amount(sample.sale_price_difference),
        parse_amount(sample.amount_difference),
    ]
    has_difference = any(value is not None and value != 0 for value in differences)
    if not has_n and not has_difference:
        return []
    text = " ".join(filter(None, (sample.evidence_description, " ".join(test.notes))))
    if any(term in text for term in ("异常", "差异原因", "跟进", "解决", "处理")):
        return []
    return [
        _issue(
            "disposal_exception_followup",
            "exception_summary",
            Severity.NEED_REVIEW,
            f"K.02.2 样本存在测试属性否定结果或金额差异，但未识别到明确异常跟进：{_identity(sample)}。",
            "记录差异原因、追加程序、处理结果和最终结论。",
            test.source_sheet,
            sample.source_row,
        )
    ]


def _identity(sample: DisposalTestedSampleRow) -> str:
    return sample.asset_id or sample.asset_name or f"第{sample.source_row}行"


def _issue(
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    source_sheet: str,
    source_row: int | None,
) -> QcIssue:
    return QcIssue(None, rule_id, field, severity, message, suggestion, "K.02.2", source_sheet, source_row)
