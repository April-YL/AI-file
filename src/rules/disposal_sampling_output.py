from __future__ import annotations

import re
from decimal import Decimal

from ingest.disposal_test_sheet import DisposalSampleOutputDataset, DisposalTestSheetDataset
from ingest.lead_sheet import CraAssertionRow, LeadSheetDataset
from ingest.records import DisposalListSummary
from rules.lead_common import cra_tier, field_values
from rules.models import QcIssue, Severity
from rules.parsing import amount_tolerance, parse_amount

RULE_IDS = (
    "disposal_sample_pool_amount_match",
    "disposal_sampling_te_cra_consistency",
    "disposal_sample_replacement_reason",
)
_RISK_RANK = {"lowest": 0, "low": 1, "moderate": 2, "high": 3}


def run_disposal_sampling_rules(
    *,
    disposal_list_summary: DisposalListSummary | None,
    disposal_test: DisposalTestSheetDataset | None,
    disposal_sample_output: DisposalSampleOutputDataset | None,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    if disposal_sample_output is None:
        return []
    if not disposal_sample_output.usable_for_rules:
        return [
            _issue(
                "disposal_sample_pool_amount_match",
                "sample_output_readability",
                Severity.NEED_REVIEW,
                "K.02.2a 选样输出未达到确定性规则执行条件。",
                "人工确认样本池、抽样参数和已选样本读取结果。",
                disposal_sample_output.source_sheet,
            )
        ]
    issues = check_disposal_sample_pool_amount(disposal_list_summary, disposal_sample_output)
    issues.extend(check_disposal_sampling_te_cra(disposal_sample_output, lead))
    issues.extend(check_disposal_sample_replacement_reason(disposal_test))
    return issues


def check_disposal_sample_pool_amount(
    summary: DisposalListSummary | None,
    sample_output: DisposalSampleOutputDataset,
) -> list[QcIssue]:
    item = sample_output.amounts.get("sample_pool_amount")
    pool = parse_amount(item.amount if item else None)
    if pool is None or summary is None:
        return [
            _issue(
                "disposal_sample_pool_amount_match",
                "sample_pool_amount",
                Severity.NEED_REVIEW,
                "未能可靠核对 K.02.2a 样本池总体金额与处置清单出售/报废总体。",
                "确认样本池金额及处置清单出售/报废净值汇总。",
                sample_output.source_sheet,
                item.source_row if item else None,
            )
        ]
    expected = parse_amount(summary.sale_scrap_net_value) or Decimal("0")
    diff = pool - expected
    if abs(diff) <= amount_tolerance(max(abs(pool), abs(expected), Decimal("1"))):
        return []
    return [
        _issue(
            "disposal_sample_pool_amount_match",
            "sample_pool_amount",
            Severity.FAIL,
            f"K.02.2a 样本池总体金额与处置清单出售/报废净值不一致：样本池={pool}，处置清单={expected}，差异={diff}。",
            "核对导入选样工具的总体是否仅包含出售和报废项目，是否遗漏或混入其他减少。",
            sample_output.source_sheet,
            item.source_row if item else None,
        )
    ]


def check_disposal_sampling_te_cra(
    sample_output: DisposalSampleOutputDataset,
    lead: LeadSheetDataset | None,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    te_item = sample_output.parameters.get("te")
    sample_te = parse_amount(te_item.value if te_item else None)
    lead_te = parse_amount(field_values(lead).get("te")) if lead else None
    if sample_te is None or lead_te is None:
        issues.append(
            _issue(
                "disposal_sampling_te_cra_consistency",
                "te",
                Severity.NEED_REVIEW,
                "未能可靠核对 K.02.2a TE 与 Lead TE。",
                "确认 K.02.2a 与 Lead 页 TE 均已填写并可读取。",
                sample_output.source_sheet,
                te_item.source_row if te_item else None,
            )
        )
    elif abs(sample_te - lead_te) > amount_tolerance(max(abs(sample_te), abs(lead_te), Decimal("1"))):
        issues.append(
            _issue(
                "disposal_sampling_te_cra_consistency",
                "te",
                Severity.FAIL,
                f"K.02.2a TE 与 Lead TE 不一致：K.02.2a={sample_te}，Lead={lead_te}。",
                "确认处置选样使用最新 Lead TE。",
                sample_output.source_sheet,
                te_item.source_row if te_item else None,
            )
        )

    cra_item = sample_output.parameters.get("cra")
    sample_cra = cra_tier(cra_item.value if cra_item else None)
    expected_cra = _expected_cra(sample_output, lead)
    if sample_cra is None or expected_cra is None:
        issues.append(
            _issue(
                "disposal_sampling_te_cra_consistency",
                "cra",
                Severity.NEED_REVIEW,
                "未能可靠核对 K.02.2a 综合风险评估与 Lead CRA。",
                "根据 K.02.2a 涵盖认定，人工核对 Lead 对应 CRA。",
                sample_output.source_sheet,
                cra_item.source_row if cra_item else None,
            )
        )
    elif sample_cra != expected_cra:
        issues.append(
            _issue(
                "disposal_sampling_te_cra_consistency",
                "cra",
                Severity.FAIL,
                f"K.02.2a 综合风险评估与 Lead 相关认定 CRA 不一致：K.02.2a={sample_cra}，Lead={expected_cra}。",
                "确认选样工具综合风险评估与 Lead 相关认定一致。",
                sample_output.source_sheet,
                cra_item.source_row if cra_item else None,
            )
        )
    return issues


def check_disposal_sample_replacement_reason(
    disposal_test: DisposalTestSheetDataset | None,
) -> list[QcIssue]:
    if disposal_test is None:
        return []
    notes = " ".join(disposal_test.notes)
    issues: list[QcIssue] = []
    for sample in disposal_test.tested_samples:
        if "替换" not in _norm(sample.sample_type) and "replacement" not in _norm(sample.sample_type):
            continue
        reason = " ".join(text for text in (sample.evidence_description, notes) if text)
        if any(term in _norm(reason) for term in ("替换原因", "原样本", "无法使用", "无法测试", "replacementreason")):
            continue
        issues.append(
            _issue(
                "disposal_sample_replacement_reason",
                "replacement_sample",
                Severity.NEED_REVIEW,
                f"K.02.2 存在替换样本，但未识别到原样本无法使用的明确原因：{sample.asset_id or sample.asset_name or sample.source_row}。",
                "补充原样本无法测试的原因及替换依据。",
                disposal_test.source_sheet,
                sample.source_row,
            )
        )
    return issues


def _expected_cra(
    sample_output: DisposalSampleOutputDataset,
    lead: LeadSheetDataset | None,
) -> str | None:
    if lead is None or not lead.cra_rows:
        return None
    assertions = sample_output.parameters.get("covered_assertions")
    keys = _assertion_keys(assertions.value if assertions else None)
    relevant = [row for row in lead.cra_rows if not keys or keys & _assertion_keys(row.assertion)]
    tiers = [cra_tier(row.cra) for row in relevant]
    tiers = [tier for tier in tiers if tier]
    return max(tiers, key=lambda tier: _RISK_RANK.get(tier, -1)) if tiers else None


def _assertion_keys(text: str | None) -> set[str]:
    norm = _norm(text)
    keys: set[str] = set()
    if "完整" in norm or "completeness" in norm:
        keys.add("completeness")
    if "存在" in norm or "发生" in norm or "exist" in norm or "occur" in norm:
        keys.add("existence")
    if "计价" in norm or "计量" in norm or "valuation" in norm or "measurement" in norm:
        keys.add("valuation")
    if "权利" in norm or "义务" in norm or "right" in norm or "obligation" in norm:
        keys.add("rights")
    return keys


def _norm(value: str | None) -> str:
    return re.sub(r"[\s_\-（）()，,、/]", "", str(value or "").strip().lower())


def _issue(
    rule_id: str,
    field: str,
    severity: Severity,
    message: str,
    suggestion: str,
    source_sheet: str,
    source_row: int | None = None,
) -> QcIssue:
    return QcIssue(None, rule_id, field, severity, message, suggestion, "K.02.2", source_sheet, source_row)
