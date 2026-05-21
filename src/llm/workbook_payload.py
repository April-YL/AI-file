"""整底稿结构化摘录，供 LLM prompt 使用（脱敏 + 体积上限）。"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.reconciliation import ReconciliationCheck
from ingest.rollforward_sheet import RollforwardSheetDataset
from ingest.summary_sheet import SummarySheetDataset
from ingest.workbook_context import WorkbookQcContext
from llm.redact import redact_value_tree

_DEFAULT_MAX_FA_RECORDS = 25
_DEFAULT_MAX_LIST_RECORDS = 15
_DEFAULT_MAX_NOTES_CHARS = 4000
_DEFAULT_MAX_PROGRAMS = 80


def _max_fa_records() -> int:
    return int(os.getenv("FA_QC_LLM_MAX_FA_RECORDS", str(_DEFAULT_MAX_FA_RECORDS)))


def _max_list_records() -> int:
    return int(os.getenv("FA_QC_LLM_MAX_LIST_RECORDS", str(_DEFAULT_MAX_LIST_RECORDS)))


def _max_programs() -> int:
    return int(os.getenv("FA_QC_LLM_MAX_SUMMARY_PROGRAMS", str(_DEFAULT_MAX_PROGRAMS)))


def _decimal_str(v: Decimal | None) -> str | None:
    if v is None:
        return None
    return str(v)


def _fa_record_row(rec: Any) -> dict[str, Any]:
    return {
        "asset_id": rec.asset_id,
        "asset_name": rec.asset_name,
        "asset_category": rec.asset_category,
        "original_value": rec.original_value,
        "accumulated_depreciation": rec.accumulated_depreciation,
        "impairment_provision": rec.impairment_provision,
        "net_value": rec.net_value,
        "source_row": rec.source_row,
    }


def _fa_list_excerpt(ds: FaListDataset | None, *, max_records: int) -> dict[str, Any] | None:
    if ds is None or not ds.source_sheet:
        return None
    total = len(ds.records)
    sample = [_fa_record_row(r) for r in ds.records[:max_records]]
    return {
        "source_sheet": ds.source_sheet,
        "mapped_fields": [m.standard_field for m in ds.mapped_fields],
        "record_count": total,
        "records_sample": sample,
        "records_truncated": total > len(sample),
    }


def _rollforward_excerpt(rf: RollforwardSheetDataset | None) -> dict[str, Any] | None:
    if rf is None or not rf.source_sheet:
        return None
    return {
        "source_sheet": rf.source_sheet,
        "header_row": rf.header_row,
        "total_row": rf.total_row,
        "mapped_fields": [m.standard_field for m in rf.mapped_fields],
        "amount_column_bindings": [
            {
                "measure": b.measure,
                "period_role": b.period_role.value,
                "column_index": b.column_index,
                "source_header": b.source_header,
            }
            for b in rf.amount_column_bindings
        ],
        "opening_totals": {k: _decimal_str(v) for k, v in rf.opening_totals.items()},
        "ending_totals": {k: _decimal_str(v) for k, v in rf.ending_totals.items()},
        "detail_record_count": len(rf.detail_records),
        "notes": rf.notes,
    }


def _lead_excerpt(lead: LeadSheetDataset | None) -> dict[str, Any] | None:
    if lead is None or not lead.source_sheet:
        return None
    sheet = lead.source_sheet
    notes_text = lead.fluctuation_notes
    if notes_text and len(notes_text) > _DEFAULT_MAX_NOTES_CHARS:
        notes_text = notes_text[:_DEFAULT_MAX_NOTES_CHARS] + "…[truncated]"
    return {
        "source_sheet": sheet,
        "layout_variant": lead.layout_variant,
        "blocks": [
            {
                "kind": b.kind.value,
                "anchor_row": b.anchor_row,
                "start_row": b.start_row,
                "end_row": b.end_row,
            }
            for b in lead.blocks
        ],
        "basic_info": [f.to_dict(sheet) for f in lead.basic_info_fields],
        "materiality": [m.to_dict(sheet) for m in lead.materiality],
        "cra_rows": [r.to_dict(sheet) for r in lead.cra_rows],
        "expectations": [e.to_dict() for e in lead.expectations],
        "volatility": lead.volatility.to_dict() if lead.volatility else None,
        "movement_column_bindings": [b.to_dict() for b in lead.movement_bindings],
        "movement_rows": [r.to_dict() for r in lead.movement_rows],
        "fluctuation_notes": notes_text,
        "adjustment_rows": [a.to_dict() for a in lead.adjustment_rows],
        "ingest_notes": lead.notes,
    }


def _summary_excerpt(summary: SummarySheetDataset | None) -> dict[str, Any] | None:
    if summary is None or not summary.source_sheet:
        return None
    max_p = _max_programs()
    programs = [
        {
            "procedure_name": p.procedure_name,
            "sheet_ref": p.sheet_ref,
            "execution_status": p.execution_status,
            "waiver_reason": p.waiver_reason,
            "notes": p.notes,
            "is_psp": p.is_psp,
            "source_row": p.source_row,
        }
        for p in summary.programs[:max_p]
    ]
    return {
        "source_sheet": summary.source_sheet,
        "layout": summary.layout,
        "header_row": summary.header_row,
        "last_data_row": summary.last_data_row,
        "program_count": len(summary.programs),
        "programs": programs,
        "programs_truncated": len(summary.programs) > max_p,
        "column_bindings": [
            {"role": b.role, "source_header": b.source_header, "column_index": b.column_index}
            for b in summary.column_bindings
        ],
        "notes": summary.notes,
    }


def _structure_excerpt(ctx: WorkbookQcContext) -> dict[str, Any] | None:
    if ctx.structure is None:
        return None
    return ctx.structure.to_dict()


def build_workbook_llm_payload(
    ctx: WorkbookQcContext,
    *,
    procedure_code: str = "WORKBOOK",
    summary_sheet_section: dict[str, Any] | None = None,
    manual_review_sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建写入 LLM user prompt 的整底稿摘录（已脱敏）。"""
    max_fa = _max_fa_records()
    max_list = _max_list_records()

    manual_sections = manual_review_sections or []
    payload: dict[str, Any] = {
        "source_file": ctx.source_file,
        "procedure_code": procedure_code,
        "structure": _structure_excerpt(ctx),
        "summary": _summary_excerpt(ctx.summary),
        "lead": _lead_excerpt(ctx.lead),
        "rollforward": _rollforward_excerpt(ctx.rollforward),
        "fa_list": _fa_list_excerpt(ctx.fa_list, max_records=max_fa),
        "addition_list": _fa_list_excerpt(ctx.addition_list, max_records=max_list),
        "disposal_list": _fa_list_excerpt(ctx.disposal_list, max_records=max_list),
        "reconciliations": [c.to_dict() for c in ctx.reconciliations],
        "summary_sheet_section": summary_sheet_section,
        "manual_review_sections": manual_sections,
        "qc_checklist_hints": _QC_HINTS,
    }

    return redact_value_tree(payload)


_QC_HINTS = (
    "固定资产 K.00 Lead 质检关注：基础信息 TE/SAD；CRA/TT 与 GAM 区间；预期分析；"
    "引导主表与 K.01 后推 TB 列一致；超波动门槛或定性调查须 Notes+波动说明；"
    "AE-003 PSP 程序页与底稿 sheet 一致。LLM 不得修改 rules 已给出的 severity。"
)


def payload_section_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in (
        "structure",
        "summary",
        "lead",
        "rollforward",
        "fa_list",
        "addition_list",
        "disposal_list",
    ):
        if payload.get(key):
            names.append(key)
    if payload.get("reconciliations"):
        names.append("reconciliations")
    if payload.get("summary_sheet_section"):
        names.append("summary_sheet_section")
    if payload.get("manual_review_sections"):
        names.append("manual_review_sections")
    return names
