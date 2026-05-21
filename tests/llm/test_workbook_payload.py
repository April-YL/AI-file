from pathlib import Path

import pytest

from ingest.workbook_context import load_workbook_context
from llm.workbook_payload import build_workbook_llm_payload, payload_section_names
from report.pipeline import run_workbook_qc

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
WORKBOOK = FIXTURES / "workbook_with_lead.xlsx"


pytestmark = pytest.mark.skipif(not WORKBOOK.exists(), reason="fixture workbook missing")


def test_workbook_payload_includes_core_sections():
    ctx = load_workbook_context(WORKBOOK)
    report = run_workbook_qc(ctx, llm=False)
    payload = build_workbook_llm_payload(
        ctx,
        procedure_code=report.procedure_code,
        summary_sheet_section=report.summary_sheet_section,
        manual_review_sections=[
            s.to_dict() if hasattr(s, "to_dict") else s
            for s in (report.manual_review_sections or [])
        ],
    )
    sections = payload_section_names(payload)
    assert "lead" in sections
    lead = payload["lead"]
    assert lead.get("basic_info") or lead.get("materiality") or lead.get("cra_rows")
    assert "qc_checklist_hints" in payload


def test_payload_redacts_client_like_names():
    ctx = load_workbook_context(WORKBOOK)
    report = run_workbook_qc(ctx, llm=False)
    payload = build_workbook_llm_payload(
        ctx,
        procedure_code=report.procedure_code,
        summary_sheet_section=report.summary_sheet_section,
        manual_review_sections=[],
    )
    raw = str(payload)
    if "ABC公司" in raw or "XYZ" in raw:
        assert "[CLIENT]" in raw or "[ASSET_ID]" in raw
