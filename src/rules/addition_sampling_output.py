from __future__ import annotations

import re
from decimal import Decimal

from ingest.addition_test_sheet import (
    AdditionParameterItem,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
)
from ingest.lead_sheet import CraAssertionRow, LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.addition_common import sum_purchase_original_value
from rules.lead_common import cra_tier, field_values
from rules.models import QcIssue, Severity
from rules.parsing import amount_tolerance, parse_amount

RULE_POOL_AMOUNT = "addition_sample_pool_purchase_amount_match"
RULE_TE_CRA = "addition_sampling_te_cra_consistency"
RULE_ASSERTIONS = "addition_sampling_assertions_scope"
RULE_REPLACEMENT = "addition_sample_replacement_reason"

_RISK_RANK = {"lowest": 0, "low": 1, "moderate": 2, "high": 3}


def check_addition_sample_pool_purchase_amount_match(
    addition_list: FaListDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    addition_test: AdditionTestSheetDataset | None = None,
) -> list[QcIssue]:
    if addition_sample_output is None:
        return []
    item = addition_sample_output.amounts.get("sample_pool_amount")
    sample_pool = parse_amount(item.amount if item else None)
    if sample_pool is None:
        return [
            _issue(
                rule_id=RULE_POOL_AMOUNT,
                field="sample_pool_amount",
                severity=Severity.NEED_REVIEW,
                message="K.02.1a 未能可靠读取样本池金额，无法与 K.01 后推购置金额核对。",
                suggestion="请确认 K.02.1a 新增选样输出中的样本金额是否存在，并补充金额读取锚点。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
                source_col=item.source_column if item else None,
            )
        ]

    target, target_label = _rollforward_purchase_amount(addition_test, rollforward)
    if target is None:
        return [
            _issue(
                rule_id=RULE_POOL_AMOUNT,
                field="sample_pool_amount",
                severity=Severity.NEED_REVIEW,
                message=f"K.02.1a 样本池金额为 {sample_pool}，但未能读取 K.01 后推购置金额，无法完成核对。",
                suggestion="请确认 K.02.1 测试页 Breakdown 购置金额或 K.01 后推购置金额是否可读取。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
                source_col=item.source_column if item else None,
            )
        ]

    diff = sample_pool - target
    tolerance = amount_tolerance(max(abs(sample_pool), abs(target), Decimal("1")))
    if abs(diff) <= tolerance:
        return []
    return [
        _issue(
            rule_id=RULE_POOL_AMOUNT,
            field="sample_pool_amount",
            severity=Severity.FAIL,
            message=(
                "K.02.1a 样本池金额与 K.01 后推购置金额不一致："
                f"样本池={sample_pool}，{target_label}={target}，差异={diff}。"
            ),
            suggestion="请核对 Skywind 选样输出是否使用了 K.01 后推购置金额，并检查 K.02.1 测试页 Breakdown 金额。",
            source_sheet=addition_sample_output.source_sheet,
            source_row=item.source_row if item else None,
            source_col=item.source_column if item else None,
        )
    ]


def check_addition_sampling_te_cra_consistency(
    addition_sample_output: AdditionSampleOutputDataset | None,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    if addition_sample_output is None:
        return []
    issues: list[QcIssue] = []
    issues.extend(_check_te(addition_sample_output, lead))
    issues.extend(_check_cra(addition_sample_output, lead))
    return issues


def check_addition_sampling_assertions_scope(
    addition_sample_output: AdditionSampleOutputDataset | None,
) -> list[QcIssue]:
    if addition_sample_output is None:
        return []
    item = addition_sample_output.parameters.get("covered_assertions")
    text = item.value if item else None
    if not text:
        return [
            _issue(
                rule_id=RULE_ASSERTIONS,
                field="covered_assertions",
                severity=Severity.NEED_REVIEW,
                message="K.02.1a 未读取到测试涵盖的认定，无法确认 TOD 测试认定范围。",
                suggestion="请核对抽样输出前置信息区是否列明测试涵盖的认定。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    if _contains_completeness_assertion(text):
        return [
            _issue(
                rule_id=RULE_ASSERTIONS,
                field="covered_assertions",
                severity=Severity.NEED_REVIEW,
                message=f"K.02.1a 测试涵盖的认定包含完整性：{text}。",
                suggestion=(
                    "一般新增 TOD 是从账面记录追查支持性证据，通常不能直接确保完整性；"
                    "请人工确认是否存在额外程序支持完整性认定。"
                ),
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    return []


def check_addition_sample_replacement_reason(
    addition_test: AdditionTestSheetDataset | None,
) -> list[QcIssue]:
    if addition_test is None:
        return []
    issues: list[QcIssue] = []
    notes_text = " ".join(addition_test.notes)
    for sample in addition_test.tested_samples:
        if not _is_replacement_sample(sample.sample_type):
            continue
        reason_text = " ".join(
            text for text in (sample.evidence_description, notes_text) if text
        )
        if _has_replacement_reason(reason_text):
            continue
        issues.append(
            _issue(
                rule_id=RULE_REPLACEMENT,
                field="replacement_sample",
                severity=Severity.NEED_REVIEW,
                message=(
                    "K.02.1 存在替换样本，但未识别到原样本无法使用的明确原因。"
                    f"样本：{sample.asset_id or sample.asset_name or sample.source_row}。"
                ),
                suggestion=(
                    "替换样本仅应在正常样本无法使用时启用，例如自动结转凭证不代表实际事项；"
                    "请补充原样本无法测试的原因和替换依据。"
                ),
                source_sheet=addition_test.source_sheet,
                source_row=sample.source_row,
            )
        )
    return issues


def _check_te(
    addition_sample_output: AdditionSampleOutputDataset,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    item = addition_sample_output.parameters.get("te")
    sample_te = parse_amount(item.value if item else None)
    if sample_te is None:
        return [
            _issue(
                rule_id=RULE_TE_CRA,
                field="te",
                severity=Severity.NEED_REVIEW,
                message="K.02.1a 未可靠读取 TE，无法与 Lead 页 TE 核对。",
                suggestion="请确认抽样输出的可容忍误差（TE）是否填写，并补充读取锚点。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    if lead is None:
        return [
            _issue(
                rule_id=RULE_TE_CRA,
                field="te",
                severity=Severity.NEED_REVIEW,
                message=f"K.02.1a TE 为 {sample_te}，但未读取到 Lead 页，无法核对。",
                suggestion="请确认工作簿包含 K.00 Lead Sheet，且 Lead 页可被识别。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    lead_te = parse_amount(field_values(lead).get("te"))
    if lead_te is None:
        return [
            _issue(
                rule_id=RULE_TE_CRA,
                field="te",
                severity=Severity.NEED_REVIEW,
                message=f"K.02.1a TE 为 {sample_te}，但 Lead 页 TE 未可靠读取。",
                suggestion="请核对 Lead 页基础信息中的 TE。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    tolerance = amount_tolerance(max(abs(sample_te), abs(lead_te), Decimal("1")))
    if abs(sample_te - lead_te) <= tolerance:
        return []
    return [
        _issue(
            rule_id=RULE_TE_CRA,
            field="te",
            severity=Severity.FAIL,
            message=f"K.02.1a TE 与 Lead 页 TE 不一致：K.02.1a={sample_te}，Lead={lead_te}。",
            suggestion="请确认 Skywind 抽样参数是否使用了最新 Lead TE；TE 不一致会影响样本量和关键项门槛。",
            source_sheet=addition_sample_output.source_sheet,
            source_row=item.source_row if item else None,
        )
    ]


def _check_cra(
    addition_sample_output: AdditionSampleOutputDataset,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    item = addition_sample_output.parameters.get("cra")
    sample_tier = cra_tier(item.value if item else None)
    if sample_tier is None:
        return [
            _issue(
                rule_id=RULE_TE_CRA,
                field="cra",
                severity=Severity.NEED_REVIEW,
                message="K.02.1a 未可靠读取综合风险评估，无法与 Lead 页 CRA 核对。",
                suggestion="请确认抽样输出是否列明综合风险评估，并注意 Skywind 中文风险等级需映射到 Lead 英文 CRA。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    if lead is None or not lead.cra_rows:
        return [
            _issue(
                rule_id=RULE_TE_CRA,
                field="cra",
                severity=Severity.NEED_REVIEW,
                message=f"K.02.1a 综合风险评估为 {item.value if item else None}，但未读取到 Lead 页 CRA。",
                suggestion="请确认 Lead 页 CRA/TT 表是否存在并可被识别。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]

    assertions = addition_sample_output.parameters.get("covered_assertions")
    covered_keys = _assertion_keys(assertions.value if assertions else None)
    relevant = _relevant_cra_rows(lead.cra_rows, covered_keys)
    if not relevant:
        return [
            _issue(
                rule_id=RULE_TE_CRA,
                field="cra",
                severity=Severity.NEED_REVIEW,
                message="未能根据 K.02.1a 测试涵盖的认定匹配 Lead 页对应 CRA 行。",
                suggestion="请人工核对 K.02.1a 综合风险评估与 Lead 页相关认定 CRA 是否一致。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    lead_tiers = [cra_tier(row.cra) for row in relevant]
    lead_tiers = [tier for tier in lead_tiers if tier]
    if not lead_tiers:
        return [
            _issue(
                rule_id=RULE_TE_CRA,
                field="cra",
                severity=Severity.NEED_REVIEW,
                message="Lead 页相关认定 CRA 未能归一化为 Minimal/Low/Moderate/High。",
                suggestion="请核对 Lead 页 CRA 填写值，并补充 CRA 映射口径。",
                source_sheet=addition_sample_output.source_sheet,
                source_row=item.source_row if item else None,
            )
        ]
    expected = max(lead_tiers, key=lambda tier: _RISK_RANK.get(tier, -1))
    if sample_tier == expected:
        return []
    lead_desc = ", ".join(f"{row.assertion}={row.cra}" for row in relevant)
    return [
        _issue(
            rule_id=RULE_TE_CRA,
            field="cra",
            severity=Severity.FAIL,
            message=(
                "K.02.1a 综合风险评估与 Lead 页相关认定 CRA 不一致："
                f"K.02.1a={item.value if item else None}（归一化 {sample_tier}），"
                f"Lead 相关认定期望为 {expected}（{lead_desc}）。"
            ),
            suggestion="请确认 Skywind 抽样参数中的综合风险评估是否与 Lead 页相关认定 CRA 一致。",
            source_sheet=addition_sample_output.source_sheet,
            source_row=item.source_row if item else None,
        )
    ]


def _relevant_cra_rows(
    cra_rows: list[CraAssertionRow],
    covered_keys: set[str],
) -> list[CraAssertionRow]:
    if not covered_keys:
        return list(cra_rows)
    out = []
    for row in cra_rows:
        row_keys = _assertion_keys(row.assertion)
        if covered_keys & row_keys:
            out.append(row)
    return out


def _assertion_keys(text: str | None) -> set[str]:
    if not text:
        return set()
    norm = _norm(text)
    keys: set[str] = set()
    if "完整" in norm or "completeness" in norm:
        keys.add("completeness")
    if "存在" in norm or "发生" in norm or "exist" in norm or "occur" in norm or "e/o" in norm:
        keys.add("existence")
    if "计价" in norm or "计量" in norm or "valuation" in norm or "measurement" in norm or "v/m" in norm:
        keys.add("valuation")
    if "权利" in norm or "义务" in norm or "right" in norm or "obligation" in norm or "r&o" in norm:
        keys.add("rights")
    if "列报" in norm or "披露" in norm or "presentation" in norm or "disclosure" in norm or "p&d" in norm:
        keys.add("presentation")
    if "截止" in norm or "cutoff" in norm:
        keys.add("cutoff")
    return keys


def _contains_completeness_assertion(text: str) -> bool:
    return "completeness" in _norm(text) or "完整" in _norm(text)


def _is_replacement_sample(sample_type: str | None) -> bool:
    text = _norm(sample_type)
    return "替换" in text or "replacement" in text


def _has_replacement_reason(text: str | None) -> bool:
    if not text:
        return False
    norm = _norm(text)
    return any(
        term in norm
        for term in (
            "替换原因",
            "原样本",
            "无法使用",
            "无法测试",
            "自动结转",
            "不代表实际事项",
            "不代表实际交易",
            "replacementreason",
            "originalsample",
        )
    )


def _norm(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"[\s_\-（）()，,、/]", "", str(value).strip().lower())



def _rollforward_purchase_amount(
    addition_test: AdditionTestSheetDataset | None,
    rollforward: RollforwardSheetDataset | None,
) -> tuple[Decimal | None, str]:
    if addition_test is not None:
        item = addition_test.amounts.get("rollforward_purchase_amount")
        amount = parse_amount(item.amount if item else None)
        if amount is not None:
            label = "K.02.1 测试页 Breakdown 购置金额"
            if getattr(item, "formula", None):
                label += "（公式/link）"
            else:
                label += "（手输/未识别公式）"
            return amount, label
    if rollforward is not None:
        amount, _row = get_movement_transaction_amount(
            rollforward,
            transaction_key="purchase",
            measure="original_value",
        )
        if amount is not None:
            return amount, "K.01 后推购置金额"
    return None, "K.01 后推购置金额"


def _issue(
    *,
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    source_sheet: str | None,
    source_row: int | None = None,
    source_col: int | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=rule_id,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.02.1",
        source_sheet=source_sheet,
        source_row=source_row,
        source_col=source_col,
    )
