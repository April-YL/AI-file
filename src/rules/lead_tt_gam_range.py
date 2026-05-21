from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    GAM_TT_RATIO_BANDS,
    cra_tier,
    field_values,
    parse_threshold_amount,
    skip_cra_module,
)
from rules.models import QcIssue, Severity

RULE_ID = "lead_tt_gam_range"


def check_lead_tt_gam_range(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """各认定 TT 占 TE 比例是否在 GAM 建议区间（资产/收入账户）。"""
    if lead is None or not lead.source_sheet or skip_cra_module(lead):
        return []
    if not lead.cra_rows:
        return []

    te = parse_threshold_amount(field_values(lead).get("te"))
    if te is None or te <= 0:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="te",
                severity=Severity.NEED_REVIEW,
                message="缺少有效 TE，无法自动核对 GAM 测试阈值区间",
                suggestion="补充 TE 后重跑，或人工对照 GAM 复核各认定 TT",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        ]

    issues: list[QcIssue] = []
    unmapped = 0
    for row in lead.cra_rows:
        tt = parse_threshold_amount(row.tt)
        if tt is None or tt <= 0:
            continue
        tier = cra_tier(row.cra)
        if tier is None:
            unmapped += 1
            continue
        band = GAM_TT_RATIO_BANDS.get(tier)
        if band is None:
            continue
        ratio = tt / te
        lo, hi = band
        if ratio < lo or ratio > hi:
            pct = (ratio * 100).quantize(Decimal("0.1"))
            lo_pct = (lo * 100).quantize(Decimal("0.1"))
            hi_pct = (hi * 100).quantize(Decimal("0.1"))
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=f"cra|tt:{row.assertion}",
                    severity=Severity.WARN,
                    message=(
                        f"认定「{row.assertion}」TT/TE={pct}% 超出 GAM 建议区间 "
                        f"{lo_pct}%–{hi_pct}%（CRA={row.cra}）"
                    ),
                    suggestion="复核 CRA 与 TT 公式是否按 GAM 区间上限/职业判断调整",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                    source_row=row.source_row,
                )
            )

    if unmapped and not issues:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="cra",
                severity=Severity.NEED_REVIEW,
                message=f"{unmapped} 行认定 CRA 无法映射至 GAM 四档，未做区间检查",
                suggestion="确认 CRA 填写为 Minimal/Low/Moderate/High 等可识别枚举",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        )
    return issues
