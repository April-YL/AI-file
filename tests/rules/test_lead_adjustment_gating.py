"""LEAD-017 合计门控：跨科目/低版式置信时不比合计。"""

from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import AdjustmentSummaryRow, LeadMovementRow, LeadSheetDataset
from ingest.lead_sheet_blocks import LeadBlock, LeadBlockKind
from rules.lead_adjustment_internal_consistency import check_lead_adjustment_internal_consistency


def _lead_main_100_summary_200() -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="t.xlsx",
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
        ],
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref=None,
                values={"audit_adjustment": "100"},
                source_row=49,
            ),
        ],
        adjustment_rows=[
            AdjustmentSummaryRow(
                adjustment_type="审计调整",
                source_row=66,
                raw_cells=["审计调整", "200"],
            ),
        ],
    )


def test_total_mismatch_when_strict_total_enabled():
    lead = _lead_main_100_summary_200()
    issues = check_lead_adjustment_internal_consistency(lead, strict_total=True)
    assert any(i.field == "adjustment_amount" for i in issues)


def test_total_skipped_when_strict_total_false():
    lead = _lead_main_100_summary_200()
    issues = check_lead_adjustment_internal_consistency(lead, strict_total=False)
    assert not any(i.field == "adjustment_amount" for i in issues)
