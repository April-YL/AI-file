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
