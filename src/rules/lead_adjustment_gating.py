"""Lead 调整汇总表 — LEAD-017 严格合计检查门控。"""

from __future__ import annotations

from typing import Any

from ingest.lead_sheet import LeadSheetDataset
from ingest.lead_sheet_blocks import LeadBlockKind

# 与 LLM 提示词共用：direct PPE 科目别名（小写归一化后子串匹配）
PPE_DIRECT_ACCOUNT_ALIASES: tuple[str, ...] = (
    "原值",
    "固定资产原值",
    "ppe cost",
    "cost",
    "累计折旧",
    "accumulated depreciation",
    "减值准备",
    "固定资产减值",
    "impairment",
    "净值",
    "net ppe",
    "net book",
    "账面价值",
)


def _norm_label(text: str | None) -> str:
    if not text:
        return ""
    return "".join(text.lower().split())


def is_direct_ppe_account(account_label: str | None) -> bool:
    n = _norm_label(account_label)
    if not n:
        return False
    for alias in PPE_DIRECT_ACCOUNT_ALIASES:
        a = _norm_label(alias)
        if a and a in n:
            return True
    return False


def should_run_strict_total_check(
    lead: LeadSheetDataset,
    *,
    layout_result: dict[str, Any] | None = None,
    extracted_rows: list[dict[str, Any]] | None = None,
) -> bool:
    """
    是否运行 LEAD-017 主表 vs 汇总表「合计」比对。

    版式未知、或仅有跨科目间接调整、或无调整块时不做严格合计。
    """
    if lead.block(LeadBlockKind.ADJUSTMENT_SUMMARY) is None:
        return False

    if layout_result:
        conf = str(layout_result.get("confidence", "")).lower()
        layout = str(layout_result.get("amount_layout", "")).lower()
        if conf == "low" or layout == "unknown":
            return False

    if extracted_rows:
        impacts = {str(r.get("ppe_impact", "")).lower() for r in extracted_rows}
        has_direct = "direct" in impacts
        has_indirect = "indirect" in impacts
        if has_indirect and not has_direct:
            return False

    return True
