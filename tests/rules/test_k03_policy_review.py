from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl

from ingest.k03_sheet import (
    EXECUTION_PATH_POLICY_REVIEW,
    INGEST_DEPTH_LIGHTWEIGHT,
    K03Area,
    K03Column,
    K03PolicyRow,
    K03PolicyTable,
    K03SheetDataset,
    K03_BRANCH_POLICY_REVIEW,
    RULE_STATUS_LATER_PHASE,
    load_k03_sheets_from_workbook,
)
from ingest.models import AssetRecord
from ingest.records import FaListDataset
from rules.k03_policy_review import (
    parse_life_range,
    parse_rate,
    run_k03_policy_review_rules,
)
from rules.models import Severity


def _policy_dataset(
    rows: list[K03PolicyRow],
    *,
    notes: str | None = "政策未见异常。",
    column_map: dict[str, K03Column] | None = None,
) -> K03SheetDataset:
    if column_map is None:
        column_map = {
            "asset_category": K03Column("固定资产类别", 1, "A", "asset_category"),
            "current_useful_life": K03Column("本期使用寿命", 5, "E", "current_useful_life"),
            "current_salvage_rate": K03Column("本期残值率", 6, "F", "current_salvage_rate"),
            "prior_useful_life": K03Column("上期使用寿命", 9, "I", "prior_useful_life"),
            "prior_salvage_rate": K03Column("上期残值率", 10, "J", "prior_salvage_rate"),
            "useful_life_same_marker": K03Column("使用寿命", 12, "L", "useful_life_same_marker"),
            "salvage_rate_same_marker": K03Column("残值率", 13, "M", "salvage_rate_same_marker"),
            "difference_explanation": K03Column("差异说明", 14, "N", "difference_explanation"),
        }
    return K03SheetDataset(
        workbook_name="policy.xlsx",
        source_file="policy.xlsx",
        sheet_name="K.03.3 折旧政策复核",
        k03_branch=K03_BRANCH_POLICY_REVIEW,
        execution_path=EXECUTION_PATH_POLICY_REVIEW,
        template_type="policy_review",
        ingest_depth=INGEST_DEPTH_LIGHTWEIGHT,
        rule_status=RULE_STATUS_LATER_PHASE,
        policy_table=K03PolicyTable(
            range=K03Area(start_row=4, end_row=4 + len(rows), start_col=1, end_col=14),
            header_row=4,
            column_map=column_map,
            rows=rows,
        ),
        note_area=(
            K03Area(start_row=10, end_row=10, start_col=1, end_col=2, text=notes)
            if notes is not None
            else None
        ),
    )


def _row(
    *,
    category: str = "机器设备",
    current_life: str = "5-10年",
    prior_life: str = "5-10年",
    current_salvage: str = "5%",
    prior_salvage: str = "5%",
    life_marker: str = "TRUE",
    salvage_marker: str = "TRUE",
    explanation: str | None = None,
) -> K03PolicyRow:
    return K03PolicyRow(
        source_row=5,
        asset_category=category,
        current_method="年限平均法",
        current_useful_life=current_life,
        current_salvage_rate=current_salvage,
        current_annual_rate="10%",
        prior_method="年限平均法",
        prior_useful_life=prior_life,
        prior_salvage_rate=prior_salvage,
        prior_annual_rate="10%",
        useful_life_same_marker=life_marker,
        salvage_rate_same_marker=salvage_marker,
        difference_explanation=explanation,
        cell_refs={"current_useful_life": "E5", "difference_explanation": "N5"},
    )


def _fa_list(records: list[AssetRecord]) -> FaListDataset:
    return FaListDataset(
        source_file="policy.xlsx",
        source_sheet="FA list",
        mapped_fields=[],
        records=records,
    )


def test_parse_policy_life_range_and_rate_formats():
    assert parse_life_range("5-10年", assume_number_unit=None).min_months == Decimal("60")
    assert parse_life_range("10年-30年", assume_number_unit=None).max_months == Decimal("360")
    assert parse_life_range("60月", assume_number_unit=None).min_months == Decimal("60")
    assert parse_life_range("60", assume_number_unit="month").min_months == Decimal("60")
    assert parse_life_range("60", assume_number_unit=None) is None

    assert parse_rate("5%") == Decimal("0.05")
    assert parse_rate("0.05") == Decimal("0.05")
    assert parse_rate("5") == Decimal("0.05")
    assert parse_rate("105%") is None


def test_complete_policy_review_does_not_report():
    ds = _policy_dataset([_row()])
    fa = _fa_list(
        [
            AssetRecord(
                source_row=8,
                asset_id="FA-TEST-001",
                asset_category="机器设备",
                useful_life_months="60",
                salvage_rate="0.05",
            )
        ]
    )

    issues = run_k03_policy_review_rules(ds, fa_list=fa)

    assert issues == []


def test_policy_change_with_true_marker_and_no_explanation_reports():
    ds = _policy_dataset(
        [_row(current_life="8年", prior_life="5年", life_marker="TRUE")],
        notes=None,
    )

    issues = run_k03_policy_review_rules(ds, fa_list=_fa_list([]))

    ids = {issue.rule_id for issue in issues}
    assert "k03_policy_difference_marker" in ids
    assert "k03_policy_change_without_explanation" in ids
    assert any(issue.severity == Severity.FAIL for issue in issues)


def test_policy_change_with_explanation_does_not_fail():
    ds = _policy_dataset(
        [
            _row(
                current_life="8年",
                prior_life="5年",
                life_marker="FALSE",
                explanation="本期更新会计估计，已取得审批。",
            )
        ],
        notes=None,
    )

    issues = run_k03_policy_review_rules(ds, fa_list=_fa_list([]))

    assert "k03_policy_change_without_explanation" not in {issue.rule_id for issue in issues}


def test_fa_list_life_and_salvage_mismatch_report_with_top_n_summary():
    ds = _policy_dataset([_row(current_life="5-10年", current_salvage="5%")])
    records = [
        AssetRecord(
            source_row=idx,
            asset_id=f"FA-TEST-{idx:03d}",
            asset_category="机器设备",
            useful_life_months="24",
            salvage_rate="10%",
        )
        for idx in range(1, 8)
    ]

    issues = run_k03_policy_review_rules(ds, fa_list=_fa_list(records))

    life_issues = [issue for issue in issues if issue.rule_id == "k03_policy_fa_life_out_of_range"]
    salvage_issues = [issue for issue in issues if issue.rule_id == "k03_policy_fa_salvage_mismatch"]
    assert len([issue for issue in life_issues if issue.source_row]) == 5
    assert len([issue for issue in salvage_issues if issue.source_row]) == 5
    assert any(issue.source_row is None for issue in life_issues)
    assert any(issue.source_row is None for issue in salvage_issues)


def test_unreadable_or_missing_policy_sheet_needs_review():
    missing = run_k03_policy_review_rules(None)
    assert missing[0].rule_id == "k03_policy_sheet_missing"
    assert missing[0].severity == Severity.NEED_REVIEW

    unreadable = _policy_dataset([])
    unreadable.policy_table = None
    issues = run_k03_policy_review_rules(unreadable)
    assert issues[0].rule_id == "k03_policy_table_unreadable"
    assert issues[0].severity == Severity.NEED_REVIEW


def test_policy_review_ingest_extracts_table_and_notes(tmp_path: Path):
    path = tmp_path / "policy.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.03.3 折旧政策复核"
    ws.append(["程序说明", "复核折旧政策是否与上期一致"])
    ws.append([])
    ws.append(["表1：公司折旧政策对比表"])
    ws.append(
        [
            "固定资产类别",
            "本期日期",
            "上期日期",
            "本期折旧方法",
            "本期使用寿命",
            "本期残值率",
            "本期年折旧率",
            "上期折旧方法",
            "上期使用寿命",
            "上期残值率",
            "上期年折旧率",
            "使用寿命 TRUE/FALSE",
            "残值率 TRUE/FALSE",
            "差异说明",
        ]
    )
    ws.append(["机器设备", "2025/12/31", "2024/12/31", "年限平均法", "5-10年", "5%", "10%", "年限平均法", "5-10年", "5%", "10%", "TRUE", "TRUE", None])
    ws.append([])
    ws.append(["Notes", "政策未见变化"])
    wb.save(path)
    wb.close()

    ds = load_k03_sheets_from_workbook(path)[0]

    assert ds.execution_path == EXECUTION_PATH_POLICY_REVIEW
    assert ds.policy_table is not None
    assert ds.policy_table.range is not None
    assert ds.policy_table.rows[0].asset_category == "机器设备"
    assert ds.policy_table.column_map["current_useful_life"].column_letter == "E"
    assert ds.note_area is not None
    assert ds.llm_candidate_context["policy_table_summary"]["row_count"] == 1
    assert "rows" not in ds.llm_candidate_context["policy_table_summary"]
