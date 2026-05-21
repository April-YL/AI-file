from __future__ import annotations

from pathlib import Path

import pytest

from report.pipeline import run_workbook_qc_from_path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_workbook_with_lead_includes_lead_section_and_rules():
    path = FIXTURES / "workbook_with_lead.xlsx"
    if not path.is_file():
        pytest.skip("fixture missing")
    report = run_workbook_qc_from_path(str(path))
    assert "lead_required_fields" in report.rule_ids
    assert report.lead_sheet_section is not None
    assert report.lead_sheet_section["ingested"] is True
    req = report.lead_sheet_section["lead_qc"]["rules"]["lead_required_fields"]
    assert req["issue_count"] >= 1
