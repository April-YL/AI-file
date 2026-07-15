from decimal import Decimal

from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalReconciliationCell,
    DisposalReconciliationMatrix,
    DisposalReconciliationRow,
    DisposalTestSheetDataset,
)
from ingest.models import AmountGroupStatus
from ingest.records import DisposalListSummary, DisposalMethodBucket
from rules.disposal_reconciliation import (
    check_disposal_reconciliation_formula_source,
    run_disposal_reconciliation_rules,
)
from rules.models import Severity


def _cell(value: str, row: int, col: int, formula: str | None = None) -> DisposalReconciliationCell:
    return DisposalReconciliationCell(value=value, formula=formula, source_row=row, source_column=col)


def _row(key: str, row: int, values: tuple[str, str, str, str], source: str) -> DisposalReconciliationRow:
    formulas = (
        f"={source}!A1",
        f"={source}!A2",
        f"={source}!A3",
        f"=G{row}-I{row}-K{row}",
    )
    return DisposalReconciliationRow(
        row_key=key,
        label=key,
        source_row=row,
        measures={
            "original_value": _cell(values[0], row, 7, formulas[0]),
            "accumulated_depreciation": _cell(values[1], row, 9, formulas[1]),
            "impairment_provision": _cell(values[2], row, 11, formulas[2]),
            "net_value": _cell(values[3], row, 5, formulas[3]),
        },
    )


def _matrix(
    *,
    usable: bool = True,
    list_original: str = "1000",
    list_accumulated: str = "700",
    list_impairment: str = "0",
    list_net: str = "300",
    rollforward_original: str = "1000",
    rollforward_accumulated: str = "700",
    rollforward_impairment: str = "0",
    rollforward_net: str = "300",
) -> DisposalReconciliationMatrix:
    return DisposalReconciliationMatrix(
        header_row=13,
        measure_columns={
            "net_value": 5,
            "original_value": 7,
            "accumulated_depreciation": 9,
            "impairment_provision": 11,
        },
        rows={
            "disposal_list": _row(
                "disposal_list",
                14,
                (list_original, list_accumulated, list_impairment, list_net),
                "'处置清单'",
            ),
            "rollforward": _row(
                "rollforward",
                15,
                (
                    rollforward_original,
                    rollforward_accumulated,
                    rollforward_impairment,
                    rollforward_net,
                ),
                "'K.01 Agree SL to GL'",
            ),
            "difference": _row("difference", 16, ("0", "0", "0", "0"), "A"),
            "investigation": DisposalReconciliationRow(
                row_key="investigation",
                label="是否调查",
                source_row=17,
                measures={
                    "original_value": _cell("否", 17, 7),
                    "accumulated_depreciation": _cell("否", 17, 9),
                    "impairment_provision": _cell("否", 17, 11),
                    "net_value": _cell("否", 17, 5),
                },
            ),
        },
        recognition_confidence=0.95 if usable else 0.5,
        usable_for_rules=usable,
        missing_components=[] if usable else ["rollforward"],
    )


def _summary() -> DisposalListSummary:
    return DisposalListSummary(
        source_file="test.xlsx",
        source_sheet="处置清单",
        record_count=1,
        buckets=[
            DisposalMethodBucket(
                bucket_key="sale",
                bucket_label="出售",
                record_count=1,
                original_value_total="1000",
                accumulated_depreciation_total="700",
                impairment_provision_total="0",
                net_value_total="300",
            )
        ],
    )


def test_low_confidence_matrix_only_outputs_readability_review():
    test = DisposalTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2 处置测试",
        reconciliation_matrix=_matrix(usable=False),
    )
    issues = run_disposal_reconciliation_rules(
        disposal_list_summary=_summary(),
        disposal_test=test,
        disposal_execution_path=None,
        rollforward=None,
        lead=None,
    )
    assert [issue.rule_id for issue in issues] == ["disposal_reconciliation_readability"]
    assert issues[0].severity == Severity.NEED_REVIEW


def test_reconciliation_warns_when_list_and_k022_disagree():
    test = DisposalTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2 处置测试",
        reconciliation_matrix=_matrix(list_original="1100", list_net="400"),
    )
    issues = run_disposal_reconciliation_rules(
        disposal_list_summary=_summary(),
        disposal_test=test,
        disposal_execution_path=None,
        rollforward=None,
        lead=None,
    )
    recon = [issue for issue in issues if issue.rule_id == "disposal_rollforward_reconciliation"]
    assert len(recon) == 1
    assert recon[0].severity == Severity.WARN
    assert recon[0].field == "reconciliation_matrix"
    assert "处置清单汇总=1000" in recon[0].message
    assert "K.02.2 处置/报废总金额=1100" in recon[0].message
    assert "原值" in recon[0].message
    assert "并导致净值差异" in recon[0].message


def test_reconciliation_merges_multiple_component_and_derived_net_differences():
    test = DisposalTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2 处置测试",
        reconciliation_matrix=_matrix(
            list_original="1300",
            list_accumulated="800",
            list_net="500",
            rollforward_original="1000",
            rollforward_accumulated="700",
            rollforward_net="300",
        ),
    )
    issues = run_disposal_reconciliation_rules(
        disposal_list_summary=_summary(),
        disposal_test=test,
        disposal_execution_path=None,
        rollforward=None,
        lead=None,
    )
    recon = [issue for issue in issues if issue.rule_id == "disposal_rollforward_reconciliation"]
    assert len(recon) == 1
    message = recon[0].message
    assert "原值" in message
    assert "累计折旧" in message
    assert "K.02.2 处置/报废总金额" in message
    assert "K.02.2 Breakdown" in message
    assert "并导致净值差异" in message


def test_reconciliation_keeps_net_difference_in_same_issue_when_components_match():
    test = DisposalTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2 处置测试",
        reconciliation_matrix=_matrix(list_net="350"),
    )
    issues = run_disposal_reconciliation_rules(
        disposal_list_summary=_summary(),
        disposal_test=test,
        disposal_execution_path=None,
        rollforward=None,
        lead=None,
    )
    recon = [issue for issue in issues if issue.rule_id == "disposal_rollforward_reconciliation"]
    assert len(recon) == 1
    assert "计算净值" in recon[0].message
    assert "并导致净值差异" not in recon[0].message


def test_formula_source_flags_wrong_reference():
    matrix = _matrix()
    row = matrix.rows["rollforward"]
    for cell in row.measures.values():
        cell.formula = "=OtherSheet!A1"
    issues = check_disposal_reconciliation_formula_source(matrix, "K.02.2 处置测试")
    assert len(issues) == 1
    assert issues[0].severity == Severity.FAIL
    assert issues[0].field == "rollforward"


def test_summary_waived_skips_reconciliation_rules():
    issues = run_disposal_reconciliation_rules(
        disposal_list_summary=_summary(),
        disposal_test=None,
        disposal_execution_path=DisposalExecutionPathDataset(
            path_kind="summary_waived",
            recognition_confidence=0.8,
        ),
        rollforward=None,
        lead=None,
    )
    assert issues == []


def test_reconciliation_does_not_compare_unconfirmed_amount_group():
    summary = _summary()
    summary.amount_group_status = AmountGroupStatus.INCOMPLETE
    test = DisposalTestSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.02.2",
        reconciliation_matrix=_matrix(list_original="1100", list_net="400"),
    )

    issues = run_disposal_reconciliation_rules(
        disposal_list_summary=summary,
        disposal_test=test,
        disposal_execution_path=None,
        rollforward=None,
        lead=None,
    )

    recon = [issue for issue in issues if issue.rule_id == "disposal_rollforward_reconciliation"]
    assert len(recon) == 1
    assert recon[0].severity == Severity.NEED_REVIEW
    assert recon[0].field == "amount_group"
