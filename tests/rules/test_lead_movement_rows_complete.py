from __future__ import annotations

from ingest.lead_sheet import LeadMovementColumnBinding, LeadMovementRow, LeadSheetDataset
from rules.lead_movement_rows_complete import check_lead_movement_rows_complete
from rules.models import Severity


def test_net_value_row_exempt_from_sheet_ref_warn():
    lead = LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        movement_bindings=[
            LeadMovementColumnBinding(
                role="sheet_ref", source_header="索引号", column_index=4
            ),
            LeadMovementColumnBinding(
                role="audited_ending", source_header="期末审定数", column_index=9
            ),
            LeadMovementColumnBinding(
                role="py_audited", source_header="上期末审定数", column_index=10
            ),
        ],
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref="K.01",
                values={"audited_ending": "100", "py_audited": "90"},
                source_row=49,
            ),
            LeadMovementRow(
                account_label="累计折旧",
                sheet_ref="K.01",
                values={"audited_ending": "50", "py_audited": "40"},
                source_row=50,
            ),
            LeadMovementRow(
                account_label="减值准备",
                sheet_ref="K.01",
                values={"audited_ending": "0", "py_audited": "0"},
                source_row=51,
            ),
            LeadMovementRow(
                account_label="净值",
                sheet_ref=None,
                values={"audited_ending": "10", "py_audited": "9"},
                source_row=53,
            ),
        ],
    )
    issues = check_lead_movement_rows_complete(lead)
    assert not any("sheet_ref" in (i.field or "") for i in issues)


def test_sheet_ref_read_from_row_attribute_not_values():
    lead = LeadSheetDataset(
        source_file="t.xlsx",
        source_sheet="K.00 Lead Sheet",
        movement_bindings=[
            LeadMovementColumnBinding(
                role="sheet_ref", source_header="索引号", column_index=4
            ),
            LeadMovementColumnBinding(
                role="audited_ending", source_header="期末审定数", column_index=9
            ),
            LeadMovementColumnBinding(
                role="py_audited", source_header="上期末审定数", column_index=10
            ),
        ],
        movement_rows=[
            LeadMovementRow(
                account_label="原值",
                sheet_ref="K.01",
                values={"audited_ending": "100", "py_audited": "90"},
                source_row=49,
            ),
            LeadMovementRow(
                account_label="累计折旧",
                sheet_ref="K.01",
                values={"audited_ending": "50", "py_audited": "40"},
                source_row=50,
            ),
            LeadMovementRow(
                account_label="减值准备",
                sheet_ref="K.01",
                values={"audited_ending": "0", "py_audited": "0"},
                source_row=51,
            ),
            LeadMovementRow(
                account_label="净值",
                sheet_ref=None,
                values={"audited_ending": "10", "py_audited": "9"},
                source_row=53,
            ),
        ],
    )
    issues = check_lead_movement_rows_complete(lead)
    assert not issues
