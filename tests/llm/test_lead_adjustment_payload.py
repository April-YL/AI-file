"""调整汇总 LLM payload 与 LEAD-017 门控单测（不调用 API）。"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from ingest.lead_adjustment_grid import build_adjustment_grid
from ingest.lead_sheet import AdjustmentSummaryRow, LeadMovementRow, LeadSheetDataset, parse_lead_sheet_rows
from ingest.lead_sheet_blocks import LeadBlock, LeadBlockKind
from llm.lead_adjustment_review import (
    build_adjustment_review_payload,
    build_guidance_adjustments,
    should_review_adjustments,
)
from rules.lead_adjustment_gating import is_direct_ppe_account, should_run_strict_total_check


def _minimal_lead_with_adjustment_block() -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        blocks=[
            LeadBlock(
                kind=LeadBlockKind.ADJUSTMENT_SUMMARY,
                anchor_row=64,
                start_row=64,
                end_row=80,
                confidence=0.9,
                anchor_text="调整汇总表",
            ),
            LeadBlock(
                kind=LeadBlockKind.MOVEMENT_TABLE,
                anchor_row=40,
                start_row=40,
                end_row=60,
                confidence=0.9,
                anchor_text="引导主表",
            ),
        ],
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref="K.01",
                values={"audit_adjustment": "100", "book_adjustment": None},
                source_row=49,
            ),
        ],
        adjustment_rows=[
            AdjustmentSummaryRow(
                adjustment_type="未更正审计调整",
                source_row=66,
                raw_cells=["未更正审计调整", "AA1", "原值", "100"],
            ),
        ],
    )


def test_should_review_when_adjustment_rows_present():
    lead = _minimal_lead_with_adjustment_block()
    assert should_review_adjustments(lead) is True


def test_should_review_when_main_has_adjustment_only():
    lead = _minimal_lead_with_adjustment_block()
    lead.adjustment_rows = []
    assert should_review_adjustments(lead) is True


def test_build_guidance_adjustments():
    lead = _minimal_lead_with_adjustment_block()
    guidance = build_guidance_adjustments(lead)
    assert guidance[0]["account_label"] == "原值"
    assert guidance[0]["audit_adjustment"] == "100"


def test_build_adjustment_review_payload_includes_grid_and_policy():
    lead = _minimal_lead_with_adjustment_block()
    payload = build_adjustment_review_payload(
        lead,
        adjustment_grid={"grid": [["调整类型", "金额"], ["审计调整", "100"]]},
        deterministic_hints=[{"rule_id": "lead_adjustment_internal_consistency"}],
    )
    assert payload["cross_account_policy"] == "flag_not_fail"
    assert payload["adjustment_grid"] == [["调整类型", "金额"], ["审计调整", "100"]]
    assert len(payload["guidance_adjustments"]) == 1
    assert "原值" in payload["ppe_direct_aliases"]


def test_is_direct_ppe_account():
    assert is_direct_ppe_account("固定资产-原值") is True
    assert is_direct_ppe_account("管理费用") is False


def test_strict_total_gated_by_low_layout():
    lead = _minimal_lead_with_adjustment_block()
    assert should_run_strict_total_check(
        lead,
        layout_result={"confidence": "low", "amount_layout": "unknown"},
    ) is False


def test_strict_total_off_for_indirect_only_rows():
    lead = _minimal_lead_with_adjustment_block()
    assert should_run_strict_total_check(
        lead,
        layout_result={"confidence": "high", "amount_layout": "single_signed_column"},
        extracted_rows=[{"ppe_impact": "indirect", "account_label": "管理费用"}],
    ) is False


def test_strict_total_on_for_direct_rows():
    lead = _minimal_lead_with_adjustment_block()
    assert should_run_strict_total_check(
        lead,
        layout_result={"confidence": "high", "amount_layout": "single_signed_column"},
        extracted_rows=[{"ppe_impact": "direct", "account_label": "原值"}],
    ) is True


@pytest.fixture
def lead_grid_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "lead_adj.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.00 Lead Sheet"
    ws["B64"] = "调整汇总表（如不适用请删除）"
    ws["B65"] = "调整类型"
    ws["C65"] = "Ref"
    ws["D65"] = "Account"
    ws["E65"] = "Amount"
    ws["B66"] = "未更正审计调整"
    ws["C66"] = "AA1"
    ws["D66"] = "原值"
    ws["E66"] = 100
    wb.save(path)
    wb.close()
    return path


def test_build_adjustment_grid_from_workbook(lead_grid_xlsx: Path):
    rows = []
    wb = openpyxl.load_workbook(lead_grid_xlsx, data_only=True)
    ws = wb["K.00 Lead Sheet"]
    for row in ws.iter_rows(max_row=80, values_only=True):
        rows.append(row)
    wb.close()
    lead = parse_lead_sheet_rows(rows, source_file=str(lead_grid_xlsx))
    grid = build_adjustment_grid(rows, lead)
    assert grid is not None
    assert grid["grid_row_count"] >= 2
    assert any("调整类型" in (c or "") for row in grid["grid"] for c in row if c)
