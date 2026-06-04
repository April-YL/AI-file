"""K.01 后推表质检结果写入报告（JSON/HTML/UI），与 lead_sheet_section 对称。"""

from __future__ import annotations

from typing import Any

from ingest.rollforward_sheet import K01_SECTION_IDS, RollforwardSheetDataset
from report.summary import worst_severity
from rules.models import QcIssue, Severity
from rules.rollforward_runner import ROLLFORWARD_RULE_IDS

_DICT_CODES: dict[str, str | None] = {
    "rollforward_exists": "GL-006",
    "rollforward_columns_complete": "GL-007",
    "rollforward_abnormal_amounts": "GL-005",
    "rollforward_fa_list_reconciliation": "GL-002",
    "rollforward_difference_over_sad": "GL-008",
    "rollforward_depreciation_pl_reconciliation": "GL-004",
    "rollforward_notes_semantic": "GL-009",
}

_MAX_BINDINGS = 24
_MAX_CONFLICTS = 12


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


def build_rollforward_sheet_section(
    rollforward: RollforwardSheetDataset,
    rollforward_issues: list[QcIssue],
) -> dict[str, Any]:
    """生成写入 ``QcReport.rollforward_sheet_section`` 的结构。"""
    rf_only = [i for i in rollforward_issues if i.rule_id in ROLLFORWARD_RULE_IDS]
    overall = worst_severity([i.severity for i in rf_only]) if rf_only else Severity.PASS

    bindings = [
        {
            "measure": b.measure,
            "period_role": b.period_role.value,
            "column_index": b.column_index,
            "source_header": b.source_header,
        }
        for b in rollforward.amount_column_bindings[:_MAX_BINDINGS]
    ]
    regions = {
        sid: {
            "anchor_row": reg.anchor_row,
            "start_row": reg.start_row,
            "end_row": reg.end_row,
            "evidence": list(reg.evidence),
        }
        for sid, reg in rollforward.section_regions.items()
    }
    sections = {
        sid: {
            "present": bool(rollforward.section_presence.get(sid)),
            "evidence": list((rollforward.section_evidence or {}).get(sid, []))[:6],
        }
        for sid in K01_SECTION_IDS
    }

    return {
        "ingested": True,
        "source_sheet": rollforward.source_sheet,
        "layout_profile": rollforward.layout_profile.value,
        "header_row": rollforward.header_row,
        "total_row": rollforward.total_row,
        "has_movement_rows": rollforward.has_movement_rows,
        "recognition_confidence": rollforward.recognition_confidence,
        "section_presence": dict(rollforward.section_presence),
        "sections": sections,
        "section_regions": regions,
        "section_conflicts": list(rollforward.section_conflicts[:_MAX_CONFLICTS]),
        "amount_column_bindings": bindings,
        "bindings_truncated": len(rollforward.amount_column_bindings) > _MAX_BINDINGS,
        "opening_totals": {
            k: str(v) for k, v in rollforward.opening_totals.items() if v is not None
        },
        "ending_totals": {
            k: str(v) for k, v in rollforward.ending_totals.items() if v is not None
        },
        "table2_amount_count": rollforward.table2_amount_count,
        "table3_check_values": [str(v) for v in rollforward.table3_check_values[:20]],
        "table3_check_row": rollforward.table3_check_row,
        "table3_notes_text_present": rollforward.table3_notes_text_present,
        "table3_notes_row": rollforward.table3_notes_row,
        "table3_notes_text": rollforward.table3_notes_text,
        "tb_reconciliation": {
            "detected": rollforward.tb_reconciliation_detected,
            "confidence": rollforward.tb_reconciliation_confidence,
            "difference_values": [str(v) for v in rollforward.tb_difference_values[:20]],
            "difference_row": rollforward.tb_difference_row,
            "notes_text_present": rollforward.tb_notes_text_present,
            "notes_row": rollforward.tb_notes_row,
            "notes_text": rollforward.tb_notes_text,
        },
        "table4_depreciation_pl": {
            "pl_amounts": [str(v) for v in rollforward.table4_pl_amounts[:20]],
            "pl_total": str(rollforward.table4_pl_total)
            if rollforward.table4_pl_total is not None
            else None,
            "pl_total_row": rollforward.table4_pl_total_row,
            "rollforward_depreciation": str(rollforward.table4_rollforward_depreciation)
            if rollforward.table4_rollforward_depreciation is not None
            else None,
            "rollforward_depreciation_row": rollforward.table4_rollforward_depreciation_row,
            "difference": str(rollforward.table4_difference)
            if rollforward.table4_difference is not None
            else None,
            "difference_row": rollforward.table4_difference_row,
            "notes_text_present": rollforward.table4_notes_text_present,
            "notes_row": rollforward.table4_notes_row,
            "notes_text": rollforward.table4_notes_text,
        },
        "ingest_notes": list(rollforward.notes or [])[:40],
        "rollforward_qc": {
            "overall_severity": overall.value,
            "issue_count": len(rf_only),
            "rules": {
                rule_id: _rule_section(rule_id, _DICT_CODES.get(rule_id), rf_only)
                for rule_id in ROLLFORWARD_RULE_IDS
            },
        },
    }
