"""Lead 表质检结果写入报告（JSON/HTML/UI），与 summary_sheet_section 对称。"""

from __future__ import annotations

from typing import Any

from ingest.lead_sheet import LeadSheetDataset
from ingest.lead_sheet_blocks import LeadBlockKind
from report.summary import worst_severity
from rules.lead_runner import LEAD_RULE_IDS
from rules.models import QcIssue, Severity

_DICT_CODES: dict[str, str | None] = {
    "materiality_consistency": "AE-001",
    "risk_threshold_consistency": "AE-002",
    "unexpected_movement_investigation": "AE-004",
    "lead_tt_overall_min": "LEAD-003",
    "lead_tt_gam_range": "LEAD-004",
    "lead_expectation_analysis": "LEAD-005",
    "lead_expectation_basis_present": "LEAD-014",
    "lead_expectation_vs_movement_review": "LEAD-015",
    "lead_volatility_threshold_link": "LEAD-006",
    "lead_movement_rows_complete": "LEAD-007",
    "lead_movement_consistency": "LEAD-008",
    "lead_movement_notes_required": "LEAD-009",
    "lead_fluctuation_notes_refs": "LEAD-016",
    "lead_adjustment_internal_consistency": "LEAD-017",
    "lead_rollforward_tb_reconciliation": "LEAD-010",
    "lead_check_with_a3_row": "LEAD-011",
}

_MAX_CRA_ROWS = 20
_MAX_MOVEMENT_ROWS = 8
_MAX_EXPECTATIONS = 12
_MAX_NOTE_CHARS = 600


def _trim_text(text: str | None) -> str | None:
    if not text:
        return text
    if len(text) > _MAX_NOTE_CHARS:
        return text[:_MAX_NOTE_CHARS] + "…"
    return text


def _blocks_payload(lead: LeadSheetDataset) -> list[dict[str, Any]]:
    return [
        {
            "kind": b.kind.value,
            "anchor_row": b.anchor_row,
            "start_row": b.start_row,
            "end_row": b.end_row,
            "confidence": b.confidence,
            "anchor_text": b.anchor_text,
        }
        for b in lead.blocks
    ]


def _rule_section(
    rule_id: str,
    dict_rule_code: str | None,
    issues: list[QcIssue],
) -> dict[str, Any]:
    subset = [i for i in issues if i.rule_id == rule_id]
    overall = worst_severity([i.severity for i in subset]) if subset else Severity.PASS
    return {
        "dict_rule_code": dict_rule_code,
        "rule_id": rule_id,
        "overall_severity": overall.value,
        "issue_count": len(subset),
        "issues": [i.to_dict() for i in subset],
    }


def build_lead_sheet_section(
    lead: LeadSheetDataset,
    lead_issues: list[QcIssue],
) -> dict[str, Any]:
    """
    生成写入 ``QcReport.lead_sheet_section`` 的结构：

    - Lead ingest 元数据、六块边界、版式变体
    - 基准信息 / CRA / 预期 / 引导表摘录（截断）
    - Lead 相关规则整体结论与 findings
    """
    lead_only = [i for i in lead_issues if i.rule_id in LEAD_RULE_IDS]
    overall = worst_severity([i.severity for i in lead_only]) if lead_only else Severity.PASS

    volatility = lead.volatility
    vol_src = volatility.amount_source if volatility else None

    basic_info = [
        f.to_dict(lead.source_sheet) for f in lead.basic_info_fields
    ]
    materiality = [m.to_dict(lead.source_sheet) for m in lead.materiality]
    cra_rows = [
        r.to_dict(lead.source_sheet) for r in lead.cra_rows[:_MAX_CRA_ROWS]
    ]
    expectations = [e.to_dict() for e in lead.expectations[:_MAX_EXPECTATIONS]]
    movement_rows = [r.to_dict() for r in lead.movement_rows[:_MAX_MOVEMENT_ROWS]]

    detected_kinds = {b.kind for b in lead.blocks}
    return {
        "ingested": True,
        "source_sheet": lead.source_sheet,
        "layout_variant": lead.layout_variant,
        "volatility_amount_source": vol_src,
        "blocks": _blocks_payload(lead),
        "blocks_detected": [k.value for k in LeadBlockKind if k in detected_kinds],
        "ingest_notes": list(lead.notes or [])[:40],
        "basic_info_fields": basic_info,
        "materiality": materiality,
        "cra_row_count": len(lead.cra_rows),
        "cra_rows": cra_rows,
        "cra_rows_truncated": len(lead.cra_rows) > _MAX_CRA_ROWS,
        "expectations": expectations,
        "volatility": volatility.to_dict() if volatility else None,
        "movement_row_count": len(lead.movement_rows),
        "movement_rows": movement_rows,
        "movement_rows_truncated": len(lead.movement_rows) > _MAX_MOVEMENT_ROWS,
        "fluctuation_notes": _trim_text(lead.fluctuation_notes),
        "adjustment_row_count": len(lead.adjustment_rows),
        "check_with_a3": (
            lead.check_with_a3.to_dict() if lead.check_with_a3 else None
        ),
        "lead_qc": {
            "overall_severity": overall.value,
            "issue_count": len(lead_only),
            "rules": {
                rule_id: _rule_section(
                    rule_id, _DICT_CODES.get(rule_id), lead_only
                )
                for rule_id in LEAD_RULE_IDS
            },
        },
    }
