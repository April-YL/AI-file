from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llm.client import LlmClientError, chat_completion_json
from llm.config import LlmConfig
from llm.router import LlmCapability, LlmRouter
from llm.prompts import SYSTEM_PROMPT, build_review_user_prompt
from llm.redact import redact_issues_for_llm, redact_programs_for_llm, redact_value_tree
from llm.workbook_payload import payload_section_names
from ingest.summary_sheet import SummarySheetDataset
from ingest.workbook_context import WorkbookQcContext
from report.summary import QcReport
from rules.models import Severity


@dataclass
class LlmEnrichment:
    """大模型对报告的增强（不改变 rules 的 severity）。"""

    model: str
    executive_summary: str
    need_review_notes: list[dict[str, Any]] = field(default_factory=list)
    lead_focus_notes: list[str] = field(default_factory=list)
    workbook_sections: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "model": self.model,
            "executive_summary": self.executive_summary,
            "need_review_notes": self.need_review_notes,
            "lead_focus_notes": self.lead_focus_notes,
            "workbook_sections": self.workbook_sections,
        }
        if self.error:
            data["error"] = self.error
        return data


def _programs_to_llm_payload(summary: SummarySheetDataset | None) -> list[dict[str, Any]]:
    if summary is None:
        return []
    rows = []
    for p in summary.programs:
        rows.append(
            {
                "procedure_name": p.procedure_name,
                "sheet_ref": p.sheet_ref,
                "execution_status": p.execution_status,
                "waiver_reason": p.waiver_reason,
                "notes": p.notes,
                "is_psp": p.is_psp,
                "source_row": p.source_row,
            }
        )
    return redact_programs_for_llm(rows)


def enrich_report_with_llm(
    report: QcReport,
    config: LlmConfig,
    *,
    summary: SummarySheetDataset | None = None,
    workbook: WorkbookQcContext | None = None,
    router: LlmRouter | None = None,
) -> QcReport:
    """在报告上附加 LLM 复核摘要；失败时写入 error，不中断规则报告。"""
    if not config.enabled:
        return report

    issues_payload = redact_issues_for_llm([i.to_dict() for i in report.issues])
    workbook_excerpt = None
    section_names: list[str] = []
    if workbook is not None:
        workbook_excerpt = _build_compact_workbook_payload(
            workbook,
            procedure_code=report.procedure_code,
            summary_sheet_section=report.summary_sheet_section,
            manual_review_sections=[
                s.to_dict() if hasattr(s, "to_dict") else s
                for s in (report.manual_review_sections or [])
            ],
        )
        section_names = payload_section_names(workbook_excerpt)

    user_prompt = build_review_user_prompt(
        source_file=report.source_file,
        procedure_code=report.procedure_code,
        issues=issues_payload,
        summary_programs=_programs_to_llm_payload(summary),
        workbook_excerpt=workbook_excerpt,
    )

    try:
        result = (router or LlmRouter(config)).complete_json(
            capability=LlmCapability.NARRATIVE,
            task="report_enrichment",
            system=SYSTEM_PROMPT,
            user=user_prompt,
            client=chat_completion_json,
        )
        enrichment = LlmEnrichment(
            model=config.model,
            executive_summary=str(result.get("executive_summary", "")).strip(),
            need_review_notes=_normalize_notes(result.get("need_review_notes", [])),
            lead_focus_notes=_normalize_lead_notes(result.get("lead_focus_notes", [])),
            workbook_sections=section_names,
        )
    except LlmClientError as e:
        enrichment = LlmEnrichment(
            model=config.model,
            executive_summary="",
            need_review_notes=[],
            lead_focus_notes=[],
            workbook_sections=section_names,
            error=str(e),
        )

    return _attach_enrichment(report, enrichment)


def _build_compact_workbook_payload(
    workbook: WorkbookQcContext,
    *,
    procedure_code: str,
    summary_sheet_section: dict[str, Any] | None,
    manual_review_sections: list[dict[str, Any]],
) -> dict[str, Any]:
    lead = workbook.lead
    rollforward = workbook.rollforward
    summary = workbook.summary
    payload: dict[str, Any] = {
        "source_file": workbook.source_file,
        "procedure_code": procedure_code,
        "summary": None,
        "lead": None,
        "rollforward": None,
        "reconciliations": [c.to_dict() for c in workbook.reconciliations[:6]],
        "summary_sheet_section": summary_sheet_section,
        "manual_review_sections": manual_review_sections[:3],
    }
    if summary is not None:
        payload["summary"] = {
            "source_sheet": summary.source_sheet,
            "layout": summary.layout,
            "program_count": len(summary.programs),
            "programs": [
                {
                    "procedure_name": p.procedure_name,
                    "sheet_ref": p.sheet_ref,
                    "execution_status": p.execution_status,
                    "waiver_reason": p.waiver_reason,
                    "source_row": p.source_row,
                }
                for p in summary.programs[:20]
            ],
        }
    if lead is not None:
        payload["lead"] = {
            "source_sheet": lead.source_sheet,
            "layout_variant": lead.layout_variant,
            "basic_info_fields": [
                f.to_dict(lead.source_sheet)
                for f in lead.basic_info_fields
                if f.field_key in {"pm", "te", "sad", "check_with_a3"}
            ],
            "materiality": [m.to_dict(lead.source_sheet) for m in lead.materiality],
            "cra_rows": [r.to_dict(lead.source_sheet) for r in lead.cra_rows[:8]],
            "expectations": [e.to_dict() for e in lead.expectations[:8]],
            "movement_rows": [r.to_dict() for r in lead.movement_rows[:8]],
            "fluctuation_notes": (lead.fluctuation_notes or "")[:1200],
            "adjustment_row_count": len(lead.adjustment_rows),
            "notes": lead.notes[:6],
        }
    if rollforward is not None:
        payload["rollforward"] = {
            "source_sheet": rollforward.source_sheet,
            "has_movement_rows": rollforward.has_movement_rows,
            "opening_totals": {
                k: str(v) for k, v in rollforward.opening_totals.items() if v is not None
            },
            "ending_totals": {
                k: str(v) for k, v in rollforward.ending_totals.items() if v is not None
            },
            "tb_difference_values": [
                str(v) for v in rollforward.tb_difference_values[:6]
            ],
            "table3_check_values": [
                str(v) for v in rollforward.table3_check_values[:6]
            ],
            "table4_difference": (
                str(rollforward.table4_difference)
                if rollforward.table4_difference is not None
                else None
            ),
            "notes": rollforward.notes[:8],
        }
    return redact_value_tree(payload)


def _normalize_notes(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    notes: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        notes.append(
            {
                "rule_id": item.get("rule_id"),
                "dict_rule_code": item.get("dict_rule_code"),
                "llm_note": item.get("llm_note", ""),
                "suggested_action": item.get("suggested_action", ""),
            }
        )
    return notes


def _normalize_lead_notes(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _attach_enrichment(report: QcReport, enrichment: LlmEnrichment) -> QcReport:
    report.llm_enrichment = enrichment
    return report


def count_need_review(report: QcReport) -> int:
    return sum(1 for i in report.issues if i.severity == Severity.NEED_REVIEW)
