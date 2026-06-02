from __future__ import annotations

from ingest.lead_sheet import (
    AdjustmentSummaryRow,
    ExpectationRow,
    LeadMovementColumnBinding,
    LeadMovementRow,
    LeadSheetDataset,
    VolatilityThreshold,
)
from rules.lead_adjustment_internal_consistency import (
    check_lead_adjustment_internal_consistency,
)
from rules.lead_expectation_basis_present import check_lead_expectation_basis_present
from rules.lead_expectation_vs_movement_review import (
    check_lead_expectation_vs_movement_review,
)
from rules.lead_fluctuation_notes_refs import check_lead_fluctuation_notes_refs
from rules.lead_runner import LEAD_RULE_IDS, run_lead_rules
from rules.models import Severity
from rules.registry import attach_rule_metadata


def _lead_with_notes() -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        volatility=VolatilityThreshold(amount="100", percent="10%"),
        movement_bindings=[
            LeadMovementColumnBinding(
                role="investigate_quantitative",
                source_header="波动幅度判断",
                column_index=11,
            ),
            LeadMovementColumnBinding(role="notes", source_header="Notes", column_index=12),
        ],
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref="K.01",
                values={
                    "movement_amount": "500",
                    "movement_pct": "20%",
                    "investigate_quantitative": "是",
                    "notes": "Note 1",
                },
                source_row=49,
            )
        ],
        fluctuation_notes="Note 2：本期新增较多，详见 K.02。",
    )


def test_fluctuation_notes_refs_warn_when_main_ref_missing_from_notes_block():
    issues = check_lead_fluctuation_notes_refs(_lead_with_notes())
    assert any(i.rule_id == "lead_fluctuation_notes_refs" and i.severity == Severity.WARN for i in issues)


def test_fluctuation_notes_refs_fail_when_triggered_row_has_no_note_ref():
    lead = _lead_with_notes()
    lead.movement_rows[0].values["notes"] = ""
    issues = check_lead_fluctuation_notes_refs(lead)
    assert any(i.rule_id == "lead_fluctuation_notes_refs" and i.severity == Severity.FAIL for i in issues)


def test_fluctuation_threshold_requires_amount_and_percent():
    lead = _lead_with_notes()
    lead.movement_bindings = [
        LeadMovementColumnBinding(role="notes", source_header="Notes", column_index=12),
    ]
    lead.movement_rows[0].values.update(
        {
            "movement_amount": "500",
            "movement_pct": "5%",
            "investigate_quantitative": "",
            "notes": "",
        }
    )
    lead.fluctuation_notes = ""

    issues = check_lead_fluctuation_notes_refs(lead)
    assert not any(i.field == "movement_notes" for i in issues)


def test_fluctuation_threshold_triggers_when_amount_and_percent_exceed():
    lead = _lead_with_notes()
    lead.movement_bindings = [
        LeadMovementColumnBinding(role="notes", source_header="Notes", column_index=12),
    ]
    lead.movement_rows[0].values.update(
        {
            "movement_amount": "500",
            "movement_pct": "20%",
            "investigate_quantitative": "",
            "notes": "",
        }
    )
    lead.fluctuation_notes = ""

    issues = check_lead_fluctuation_notes_refs(lead)
    assert any(i.field == "movement_notes" and i.severity == Severity.FAIL for i in issues)


def test_expectation_basis_warns_when_all_expectations_are_trivial():
    lead = LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        expectations=[
            ExpectationRow(account_change="新增", expectation="无重大变化", source_row=28),
            ExpectationRow(account_change="处置", expectation="合理", source_row=29),
        ],
    )
    issues = check_lead_expectation_basis_present(lead)
    assert any(i.rule_id == "lead_expectation_basis_present" and i.severity == Severity.WARN for i in issues)


def test_expectation_vs_movement_marks_review_when_no_change_expectation_conflicts_with_threshold():
    lead = LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        expectations=[
            ExpectationRow(account_change="固定资产", expectation="预计无重大变化", source_row=28),
        ],
        volatility=VolatilityThreshold(amount="100", percent="10%"),
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref="K.01",
                values={"movement_amount": "500", "movement_pct": "20%"},
                source_row=49,
            )
        ],
    )
    issues = check_lead_expectation_vs_movement_review(lead)
    assert any(
        i.rule_id == "lead_expectation_vs_movement_review"
        and i.severity == Severity.NEED_REVIEW
        for i in issues
    )


def test_expectation_vs_movement_does_not_trigger_on_amount_only():
    lead = LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        expectations=[
            ExpectationRow(account_change="固定资产", expectation="预计无重大变化", source_row=28),
        ],
        volatility=VolatilityThreshold(amount="100", percent="10%"),
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref="K.01",
                values={"movement_amount": "500", "movement_pct": "5%"},
                source_row=49,
            )
        ],
    )
    issues = check_lead_expectation_vs_movement_review(lead)
    assert issues == []


def test_adjustment_internal_consistency_fails_when_main_adjustment_has_no_summary():
    lead = LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref="K.01",
                values={"book_adjustment": "200", "audit_adjustment": "0"},
                source_row=49,
            )
        ],
    )
    issues = check_lead_adjustment_internal_consistency(lead)
    assert any(
        i.rule_id == "lead_adjustment_internal_consistency"
        and i.severity == Severity.FAIL
        for i in issues
    )


def test_adjustment_internal_consistency_warns_when_summary_has_no_main_adjustment():
    lead = LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        adjustment_rows=[
            AdjustmentSummaryRow(
                adjustment_type="审计调整",
                source_row=80,
                raw_cells=["审计调整", "200", "说明"],
            )
        ],
    )
    issues = check_lead_adjustment_internal_consistency(lead)
    assert any(
        i.rule_id == "lead_adjustment_internal_consistency"
        and i.severity == Severity.WARN
        for i in issues
    )


def test_new_lead_rules_registered_and_metadata_attached():
    expected = {
        "lead_fluctuation_notes_refs",
        "lead_expectation_basis_present",
        "lead_expectation_vs_movement_review",
        "lead_adjustment_internal_consistency",
    }
    assert expected.issubset(set(LEAD_RULE_IDS))

    lead = _lead_with_notes()
    lead.movement_rows[0].values["notes"] = ""
    lead.expectations = [
        ExpectationRow(account_change="固定资产", expectation="预计无重大变化", source_row=28)
    ]
    issues = attach_rule_metadata(run_lead_rules(lead))
    by_rule = {i.rule_id: i.dict_rule_code for i in issues}
    assert by_rule["lead_fluctuation_notes_refs"] == "LEAD-016"
    assert by_rule["lead_expectation_basis_present"] == "LEAD-014"
