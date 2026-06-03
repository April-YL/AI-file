"""K.01 后推规则单测。"""

from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadBasicInfoField, LeadSheetDataset, MaterialityCapture
from ingest.reconciliation import ReconciliationCheck, ReconciliationStatus
from ingest.models import RollforwardLayoutProfile, RollforwardPeriodRole
from ingest.rollforward_sheet import RollforwardSheetDataset, parse_rollforward_rows
from rules.registry import attach_rule_metadata, get_by_dict_code
from rules.rollforward_abnormal_amounts import check_rollforward_abnormal_amounts
from rules.rollforward_columns_complete import check_rollforward_columns_complete
from rules.rollforward_depreciation_pl_reconciliation import (
    check_rollforward_depreciation_pl_reconciliation,
)
from rules.rollforward_difference_over_sad import check_rollforward_difference_over_sad
from rules.rollforward_exists import check_rollforward_exists
from rules.rollforward_fa_list_reconciliation import check_rollforward_fa_list_reconciliation
from rules.rollforward_runner import run_rollforward_rules
from rules.models import Severity


def _minimal_rf(**kwargs) -> RollforwardSheetDataset:
  base = dict(
      source_file="test.xlsx",
      source_sheet="K.01 Agree SL to GL",
      header_row=2,
      mapped_fields=[],
      layout_profile=RollforwardLayoutProfile.HYBRID,
      has_movement_rows=True,
  )
  base.update(kwargs)
  return RollforwardSheetDataset(**base)


def _lead_with_sad(value: str | None = "5") -> LeadSheetDataset:
    fields = []
    materiality = []
    if value is not None:
        fields.append(
            LeadBasicInfoField(
                field_key="sad",
                label="名义金额 (SAD)",
                value=value,
                source_row=3,
                source_col=2,
            )
        )
        materiality.append(
            MaterialityCapture(
                field_key="sad",
                label="名义金额 (SAD)",
                workpaper_value=value,
                source_row=3,
                source_col_workpaper=2,
            )
        )
    return LeadSheetDataset(
        source_file="test.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=fields,
        materiality=materiality,
    )


def test_rollforward_exists_fail_when_missing():
    issues = check_rollforward_exists(None)
    assert len(issues) == 1
    assert issues[0].severity == Severity.FAIL


def test_rollforward_exists_pass_parseable():
    rf = _minimal_rf(
        amount_column_bindings=[],
        ending_totals={"original_value": Decimal("1")},
        section_presence={"b1_bkd_main_table": True},
    )
    assert not check_rollforward_exists(rf)


def test_rollforward_exists_fail_missing_b1_section():
    rf = _minimal_rf(
        header_row=5,
        section_presence={
            "b1_bkd_main_table": False,
            "b2_movement_tb_reconciliation": True,
        },
    )
    issues = check_rollforward_exists(rf)
    assert len(issues) == 1
    assert issues[0].severity == Severity.FAIL
    assert "表1" in issues[0].message or "BKD" in issues[0].message


def test_rollforward_columns_complete_l1_pass():
    from ingest.models import RollforwardColumnBinding

    bindings = []
    for measure in ("original_value", "accumulated_depreciation", "impairment_provision", "net_value"):
        bindings.append(
            RollforwardColumnBinding(
                measure=measure,
                period_role=RollforwardPeriodRole.OPENING,
                column_index=3,
                source_header="审2原值",
            )
        )
        bindings.append(
            RollforwardColumnBinding(
                measure=measure,
                period_role=RollforwardPeriodRole.ENDING,
                column_index=8,
                source_header="审3原值",
            )
        )
    bindings.append(
        RollforwardColumnBinding(
            measure="original_value",
            period_role=RollforwardPeriodRole.MOVEMENT,
            column_index=12,
            source_header="原值变动金额",
        )
    )
    rf = _minimal_rf(
        amount_column_bindings=bindings,
        ending_totals={"impairment_provision": Decimal("0")},
        opening_totals={"original_value": Decimal("100")},
    )
    assert not check_rollforward_columns_complete(rf)


def test_rollforward_columns_complete_fail_missing_movement():
    from ingest.models import RollforwardColumnBinding

    bindings = [
        RollforwardColumnBinding(
            measure="original_value",
            period_role=RollforwardPeriodRole.ENDING,
            column_index=3,
            source_header="原值",
        ),
    ]
    rf = _minimal_rf(
        amount_column_bindings=bindings,
        ending_totals={"original_value": Decimal("1")},
        has_movement_rows=False,
    )
    issues = check_rollforward_columns_complete(rf)
    assert issues
    assert "变动" in issues[0].message


def test_dual_period_audit_labels_ingest_and_rules():
    rows: list[tuple] = [()] * 56
    rows[51] = ("", "审2", "", "", "", "", "", "审3", "", "", "", "")
    rows[52] = ("", "汇总", "", "", "", "", "", "表2 check with 表1", "", "", "")
    rows[53] = (
        "",
        "固定资产类别",
        "原值",
        "累计折旧",
        "减值准备",
        "净值",
        "",
        "原值",
        "累计折旧",
        "减值准备",
        "净值",
    )
    rows[54] = ("", "办公设备", 100, 10, 0, 90, "", 110, 12, 0, 98)
    rows[55] = ("", "合计", 100, 10, 0, 90, "", 110, 12, 0, 98)
    rows[32] = ("", "变动", "原值变动金额", "本年VS上年", 0, 0, 0, 10)

    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    roles = {b.period_role for b in rf.amount_column_bindings}
    assert RollforwardPeriodRole.OPENING in roles
    assert RollforwardPeriodRole.ENDING in roles
    assert rf.has_movement_rows
    assert rf.layout_profile in (
        RollforwardLayoutProfile.HYBRID,
        RollforwardLayoutProfile.CATEGORY_DUAL_PERIOD,
    )

    issues = attach_rule_metadata(run_rollforward_rules(rf))
    assert not [i for i in issues if i.rule_id == "rollforward_exists"]
    assert not [i for i in issues if i.rule_id == "rollforward_columns_complete"]


def test_rollforward_ingest_extracts_table2_and_table3_check_values():
    rows = [
        ("表1", "固定资产类别", "原值", "累计折旧", "净值"),
        ("", "合计", 100, 10, 90),
        ("原值变动金额", "TB-原值", "差异"),
        ("表2", "固定资产清单"),
        ("类别", "原值", "累计折旧", "净值"),
        ("设备", 100, 10, 90),
        ("表3", "表2 check with 表1"),
        ("原值差异", 0),
        ("累计折旧差异", 0),
        ("净值差异", 1),
        ("表4", "折旧费用与利润表科目核对"),
    ]
    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    assert rf.section_presence["b3_table2_fa_summary"] is True
    assert rf.section_presence["b4_table3_check_with_table1"] is True
    assert rf.table2_amount_count >= 3
    assert Decimal("1") in rf.table3_check_values
    assert rf.table3_check_row == 8


def test_rollforward_ingest_extracts_side_by_side_table2_table3_check():
    rows = [
        ("表1",),
        ("固定资产类别", "设备", None, None, None, None, None, "合计"),
        ("", "年末余额", 100, 10, 0, 90, None, 100, 10, 0, 90),
        ("原值变动金额", "TB-原值", "差异"),
        ("表2", None, None, None, None, None, None, "表3"),
        (None, None, None, "汇总", None, None, None, "表2 check with 表1"),
        (None, "固定资产类别", "原值", "累计折旧", "减值准备", "净值", None, "原值", "累计折旧", "减值准备", "净值"),
        (None, "设备", 100, 10, 0, 90, None, 0, 0, 0, 0),
        (None, "合计", 100, 10, 0, 90, None, 0, 0, 0, 0),
        ("表4", "折旧费用与利润表科目核对"),
    ]
    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    assert rf.ending_totals["original_value"] == Decimal("100")
    assert rf.ending_totals["net_value"] == Decimal("90")
    assert rf.table2_amount_count >= 4
    assert rf.table3_check_values == [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]
    assert not all(v == 0 for v in rf.ending_totals.values() if v is not None)


def test_rollforward_ingest_extracts_tb_check_and_notes():
    rows = [
        ("表1", "固定资产类别", "原值", "累计折旧", "净值"),
        ("", "合计", 100, 10, 90),
        ("原值变动金额", "TB-原值", "差异"),
        ("与TB核对", 100, 0),
        ("累计折旧变动金额", "TB-累计折旧", "差异"),
        ("与TB核对", 8, 2),
        ("表2", "固定资产清单"),
        ("表3", "表2 check with 表1"),
        ("表4", "折旧费用与利润表科目核对"),
        ("Notes", "超过SAD差异调查", "超过TE转K.02/K.03"),
        ("说明", "累计折旧差异为重分类影响，已与项目组确认"),
    ]
    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    assert rf.section_presence["b2_movement_tb_reconciliation"] is True
    assert rf.tb_reconciliation_detected is True
    assert rf.tb_reconciliation_confidence >= 0.65
    assert Decimal("2") in rf.tb_difference_values
    assert rf.tb_difference_row in (4, 6)
    assert rf.tb_notes_text_present is True
    assert "重分类影响" in (rf.tb_notes_text or "")


def test_rollforward_ingest_does_not_use_distant_table4_notes_as_tb_notes():
    rows = [()] * 90
    rows[0] = ("表1", "固定资产类别", "原值", "累计折旧", "净值")
    rows[1] = ("", "合计", 100, 10, 90)
    rows[34] = (None, None, "累计折旧变动金额", "本年VS上年", 10)
    rows[41] = (None, "TB-原值", None, None, 100)
    rows[42] = (None, "差异", None, None, 3000000, None, None, 0, None, None, 0, None, None, 0, None, None, 0, None, None, 0, None, None, 0, None, None, 0, None, None, 3000000)
    rows[76] = (None, "表4", "折旧费用与利润表科目核对")
    rows[79] = (None, "K1", None, "TB", "累计折旧科目-本年计提", 65904751)
    rows[80] = (None, None, None, None, "差异", -3001537)
    rows[83] = (None, "Notes")
    rows[84] = (None, "将固定资产本年折旧与利润表相关科目金额核对，差异小于SAD，不执行进一步程序")

    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    assert rf.tb_reconciliation_detected is True
    assert rf.tb_notes_text_present is False
    cells = {d["cell"] for d in rf.tb_difference_details if d["value"].startswith("3000000")}
    assert {"E43", "AC43"}.issubset(cells)


def test_rollforward_ingest_does_not_treat_movement_only_as_reliable_tb_check():
    rows = [
        ("表1", "固定资产类别", "原值", "累计折旧", "净值"),
        ("", "合计", 100, 10, 90),
        ("原值变动金额", "本年VS上年", 10),
        ("表2", "固定资产清单"),
        ("表3", "表2 check with 表1"),
    ]
    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    assert rf.section_presence["b2_movement_tb_reconciliation"] is True
    assert rf.tb_reconciliation_detected is False
    assert rf.tb_reconciliation_confidence < 0.65
    assert "k01_tb_check_needs_review" in " ".join(rf.notes)


def test_rollforward_ingest_extracts_table4_depreciation_pl_check():
    rows = [
        ("表1", "固定资产类别", "原值", "累计折旧", "净值"),
        ("", "合计", 100, 10, 90),
        ("表4",),
        ("折旧费用与利润表科目核对",),
        ("账套名称/账套编码", "科目编码", "交叉索引", "科目名称", "金额"),
        ("测试公司", "6602", "U-001", "管理费用", 100),
        ("测试公司", "6604", "U-002", "研发费用", 40),
        ("", "", "", "合计", 140),
        ("K1", "", "TB", "累计折旧科目-本年计提", 130),
        ("", "", "", "差异", 10),
        ("Notes",),
        ("说明", "折旧费用差异为分类口径影响"),
    ]
    rf = parse_rollforward_rows(rows, source_sheet="K.01 Agree SL to GL")
    assert rf.section_presence["b5_table4_depreciation_pl"] is True
    assert rf.table4_pl_amounts == [Decimal("100"), Decimal("40")]
    assert rf.table4_pl_total == Decimal("140")
    assert rf.table4_rollforward_depreciation == Decimal("130")
    assert rf.table4_difference == Decimal("10")
    assert rf.table4_difference_row == 10
    assert rf.table4_notes_text_present is True
    assert "分类口径" in (rf.table4_notes_text or "")


def test_rollforward_depreciation_pl_reconciliation_fails_when_note_says_under_sad_but_diff_exceeds():
    rf = _minimal_rf(
        section_presence={"b5_table4_depreciation_pl": True},
        table4_difference=Decimal("300"),
        table4_difference_row=80,
        table4_notes_text_present=True,
        table4_notes_row=85,
        table4_notes_text="差异小于SAD，不执行进一步程序",
    )
    issues = check_rollforward_depreciation_pl_reconciliation(rf, lead=_lead_with_sad("200"))
    assert issues
    assert issues[0].severity == Severity.FAIL
    assert "超过 SAD" in issues[0].message


def test_rollforward_abnormal_amounts_fail_accum_exceeds_original():
    rf = _minimal_rf(
        section_presence={"b1_bkd_main_table": True},
        ending_totals={
            "original_value": Decimal("100"),
            "accumulated_depreciation": Decimal("150"),
            "net_value": Decimal("-50"),
        },
        total_row=10,
    )
    issues = check_rollforward_abnormal_amounts(rf)
    assert issues
    assert any(i.severity == Severity.FAIL for i in issues)
    assert any("累计折旧" in i.message for i in issues)


def test_rollforward_abnormal_amounts_fail_negative_net():
    rf = _minimal_rf(
        section_presence={"b1_bkd_main_table": True},
        ending_totals={
            "original_value": Decimal("100"),
            "accumulated_depreciation": Decimal("80"),
            "net_value": Decimal("-1"),
        },
    )
    issues = check_rollforward_abnormal_amounts(rf)
    assert any("净值为负" in i.message for i in issues)


def test_rollforward_abnormal_amounts_pass_normal_totals():
    rf = _minimal_rf(
        section_presence={"b1_bkd_main_table": True},
        ending_totals={
            "original_value": Decimal("1000"),
            "accumulated_depreciation": Decimal("400"),
            "impairment_provision": Decimal("0"),
            "net_value": Decimal("600"),
        },
    )
    assert not check_rollforward_abnormal_amounts(rf)


def _reconciliation_check(
    *,
    link_id: str = "fa_list_rollforward_net",
    status: ReconciliationStatus,
    left_value: str | None = "100",
    right_value: str | None = "90",
    difference: str | None = "10",
) -> ReconciliationCheck:
    return ReconciliationCheck(
        link_id=link_id,
        dict_rule_code="GL-002",
        name="FA list 净值与后推期末净值",
        status=status,
        left_ref="FA list!fa_list",
        right_ref="K.01 Agree SL to GL!row10",
        left_value=left_value,
        right_value=right_value,
        difference=difference,
        message="FA list 净值合计与 K.01 后推期末净值不一致",
        suggestion="调查差异是否超过 SAD，并核对底稿与台账来源",
    )


def test_rollforward_fa_list_reconciliation_table3_zero_passes():
    rf = _minimal_rf(
        section_presence={
            "b3_table2_fa_summary": True,
            "b4_table3_check_with_table1": True,
        },
        table2_amount_count=4,
        table3_check_values=[Decimal("0"), Decimal("0.00")],
        table3_check_row=30,
        total_row=10,
    )
    issues = check_rollforward_fa_list_reconciliation(
        [_reconciliation_check(status=ReconciliationStatus.MISMATCH)],
        rollforward=rf,
    )
    assert issues == []


def test_rollforward_fa_list_reconciliation_table3_difference_within_sad_passes():
    rf = _minimal_rf(
        section_presence={
            "b3_table2_fa_summary": True,
            "b4_table3_check_with_table1": True,
        },
        table2_amount_count=4,
        table3_check_values=[Decimal("0"), Decimal("4.99")],
        table3_check_row=30,
        total_row=10,
    )
    issues = check_rollforward_fa_list_reconciliation(
        [_reconciliation_check(status=ReconciliationStatus.MATCH)],
        rollforward=rf,
        lead=_lead_with_sad("5"),
    )
    assert issues == []


def test_rollforward_fa_list_reconciliation_table3_material_difference_without_note_fails():
    rf = _minimal_rf(
        section_presence={
            "b3_table2_fa_summary": True,
            "b4_table3_check_with_table1": True,
        },
        table2_amount_count=4,
        table3_check_values=[Decimal("0"), Decimal("12.34")],
        table3_check_row=30,
        total_row=10,
        tb_notes_text_present=False,
    )
    issues = check_rollforward_fa_list_reconciliation(
        [_reconciliation_check(status=ReconciliationStatus.MATCH)],
        rollforward=rf,
        lead=_lead_with_sad("5"),
    )
    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "rollforward_fa_list_reconciliation"
    assert issue.severity == Severity.FAIL
    assert issue.procedure_code == "K.01"
    assert issue.source_sheet == "K.01 Agree SL to GL"
    assert issue.source_row == 30
    assert issue.field == "table3_check_with_table1"
    assert "表3" in issue.message
    assert "12.34" in issue.message
    assert "超过 SAD" in issue.message
    assert "Notes" in issue.suggestion


def test_rollforward_fa_list_reconciliation_table3_material_difference_with_note_passes():
    rf = _minimal_rf(
        section_presence={
            "b3_table2_fa_summary": True,
            "b4_table3_check_with_table1": True,
        },
        table2_amount_count=4,
        table3_check_values=[Decimal("0"), Decimal("12.34")],
        table3_check_row=30,
        total_row=10,
        tb_notes_text_present=True,
        tb_notes_text="差异为取数口径导致，已说明",
        tb_notes_row=35,
    )
    issues = check_rollforward_fa_list_reconciliation(
        [_reconciliation_check(status=ReconciliationStatus.MATCH)],
        rollforward=rf,
        lead=_lead_with_sad("5"),
    )
    assert issues == []


def test_rollforward_fa_list_reconciliation_table3_difference_needs_review_without_sad():
    rf = _minimal_rf(
        section_presence={
            "b3_table2_fa_summary": True,
            "b4_table3_check_with_table1": True,
        },
        table2_amount_count=4,
        table3_check_values=[Decimal("12.34")],
        table3_check_row=30,
        total_row=10,
    )
    issues = check_rollforward_fa_list_reconciliation(
        [_reconciliation_check(status=ReconciliationStatus.MATCH)],
        rollforward=rf,
        lead=_lead_with_sad(None),
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].field == "table3_check_with_table1"
    assert "SAD" in issues[0].message


def test_rollforward_fa_list_reconciliation_unreadable_table3_uses_fallback_as_review():
    rf = _minimal_rf(
        section_presence={"b3_table2_fa_summary": True},
        table2_amount_count=3,
        total_row=10,
    )
    issues = check_rollforward_fa_list_reconciliation(
        [
            _reconciliation_check(
                status=ReconciliationStatus.MISMATCH,
            )
        ],
        rollforward=rf,
    )
    assert len(issues) == 2
    assert all(i.severity == Severity.NEED_REVIEW for i in issues)
    assert any(i.field == "b4_table3_check_with_table1" for i in issues)
    fallback = [i for i in issues if i.field == "fa_list_rollforward_fallback"][0]
    assert "兜底提示" in fallback.message
    assert "自算差异" in fallback.message


def test_rollforward_runner_includes_fa_list_reconciliation():
    rf = _minimal_rf(
        amount_column_bindings=[],
        ending_totals={"net_value": Decimal("90")},
        section_presence={
            "b1_bkd_main_table": True,
            "b4_table3_check_with_table1": True,
        },
        table3_check_values=[Decimal("1")],
        table3_check_row=30,
        total_row=10,
    )
    issues = run_rollforward_rules(
        rf,
        reconciliations=[_reconciliation_check(status=ReconciliationStatus.MISMATCH)],
    )
    assert any(i.rule_id == "rollforward_fa_list_reconciliation" for i in issues)


def test_rollforward_difference_over_sad_pass_when_difference_within_sad():
    rf = _minimal_rf(
        section_presence={"b2_movement_tb_reconciliation": True},
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("5"), Decimal("-4")],
        tb_difference_row=8,
    )
    issues = check_rollforward_difference_over_sad(rf, lead=_lead_with_sad("5"))
    assert issues == []


def test_rollforward_difference_over_sad_fails_when_no_note():
    rf = _minimal_rf(
        section_presence={"b2_movement_tb_reconciliation": True},
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("6")],
        tb_difference_row=8,
        tb_notes_text_present=False,
    )
    issues = check_rollforward_difference_over_sad(rf, lead=_lead_with_sad("5"))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "rollforward_difference_over_sad"
    assert issue.severity == Severity.FAIL
    assert issue.source_row == 8
    assert "超过 SAD" in issue.message
    assert "未读取到 Notes" in issue.message


def test_rollforward_difference_over_sad_fails_when_material_cells_have_no_note_marker():
    rf = _minimal_rf(
        section_presence={"b2_movement_tb_reconciliation": True},
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("6"), Decimal("7")],
        tb_difference_details=[
            {"row": 43, "column": 5, "cell": "E43", "value": "6", "note_marker": None},
            {"row": 43, "column": 29, "cell": "AC43", "value": "7", "note_marker": ""},
        ],
        tb_difference_row=43,
        tb_notes_text_present=True,
        tb_notes_row=85,
        tb_notes_text="表4折旧核对差异小于SAD",
    )
    issues = check_rollforward_difference_over_sad(rf, lead=_lead_with_sad("5"))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.FAIL
    assert issue.source_row == 43
    assert issue.field == "tb_difference_note_marker"
    assert "E43=6" in issue.message
    assert "AC43=7" in issue.message


def test_rollforward_difference_over_sad_needs_review_when_note_exists():
    rf = _minimal_rf(
        section_presence={"b2_movement_tb_reconciliation": True},
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("6")],
        tb_difference_row=8,
        tb_notes_text_present=True,
        tb_notes_row=12,
        tb_notes_text="差异为重分类影响，已与项目组确认",
    )
    issues = check_rollforward_difference_over_sad(rf, lead=_lead_with_sad("5"))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.NEED_REVIEW
    assert issue.source_row == 12
    assert "已有 Notes" in issue.message


def test_rollforward_difference_over_sad_needs_review_when_sad_missing():
    rf = _minimal_rf(
        section_presence={"b2_movement_tb_reconciliation": True},
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("6")],
        tb_difference_row=8,
    )
    issues = check_rollforward_difference_over_sad(rf, lead=_lead_with_sad(None))
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].field == "sad"


def test_rollforward_difference_over_sad_needs_review_when_tb_unreliable():
    rf = _minimal_rf(
        section_presence={"b2_movement_tb_reconciliation": True},
        tb_reconciliation_detected=False,
        tb_reconciliation_confidence=0.45,
    )
    issues = check_rollforward_difference_over_sad(rf, lead=_lead_with_sad("5"))
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].field == "tb_reconciliation"


def test_rollforward_runner_includes_difference_over_sad():
    rf = _minimal_rf(
        section_presence={
            "b1_bkd_main_table": True,
            "b2_movement_tb_reconciliation": True,
        },
        tb_reconciliation_detected=True,
        tb_difference_values=[Decimal("6")],
        tb_difference_row=8,
    )
    issues = run_rollforward_rules(rf, lead=_lead_with_sad("5"))
    assert any(i.rule_id == "rollforward_difference_over_sad" for i in issues)


def test_rollforward_depreciation_pl_reconciliation_pass_when_difference_within_sad():
    rf = _minimal_rf(
        section_presence={"b5_table4_depreciation_pl": True},
        table4_difference=Decimal("5"),
        table4_difference_row=80,
    )
    issues = check_rollforward_depreciation_pl_reconciliation(
        rf, lead=_lead_with_sad("5")
    )
    assert issues == []


def test_rollforward_depreciation_pl_reconciliation_fails_without_note():
    rf = _minimal_rf(
        section_presence={"b5_table4_depreciation_pl": True},
        table4_difference=Decimal("6"),
        table4_difference_row=80,
        table4_notes_text_present=False,
    )
    issues = check_rollforward_depreciation_pl_reconciliation(
        rf, lead=_lead_with_sad("5")
    )
    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "rollforward_depreciation_pl_reconciliation"
    assert issue.severity == Severity.FAIL
    assert issue.source_row == 80
    assert "超过 SAD" in issue.message


def test_rollforward_depreciation_pl_reconciliation_needs_review_with_note():
    rf = _minimal_rf(
        section_presence={"b5_table4_depreciation_pl": True},
        table4_difference=Decimal("6"),
        table4_difference_row=80,
        table4_notes_text_present=True,
        table4_notes_text="差异为分摊口径影响",
        table4_notes_row=85,
    )
    issues = check_rollforward_depreciation_pl_reconciliation(
        rf, lead=_lead_with_sad("5")
    )
    assert issues
    assert issues[0].severity == Severity.NEED_REVIEW


def test_rollforward_depreciation_pl_reconciliation_needs_review_without_sad():
    rf = _minimal_rf(
        section_presence={"b5_table4_depreciation_pl": True},
        table4_difference=Decimal("6"),
        table4_difference_row=80,
    )
    issues = check_rollforward_depreciation_pl_reconciliation(
        rf, lead=_lead_with_sad(None)
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].field == "sad"


def test_rollforward_depreciation_pl_reconciliation_needs_review_without_difference():
    rf = _minimal_rf(section_presence={"b5_table4_depreciation_pl": True})
    issues = check_rollforward_depreciation_pl_reconciliation(
        rf, lead=_lead_with_sad("5")
    )
    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW
    assert issues[0].field == "table4_difference"


def test_rollforward_runner_includes_depreciation_pl_reconciliation():
    rf = _minimal_rf(
        section_presence={
            "b1_bkd_main_table": True,
            "b5_table4_depreciation_pl": True,
        },
        table4_difference=Decimal("6"),
        table4_difference_row=80,
    )
    issues = run_rollforward_rules(rf, lead=_lead_with_sad("5"))
    assert any(
        i.rule_id == "rollforward_depreciation_pl_reconciliation" for i in issues
    )


def test_registry_gl005_implemented():
    spec = get_by_dict_code("GL-005")
    assert spec is not None
    assert spec.rule_id == "rollforward_abnormal_amounts"
    from rules.registry import ImplementationStatus

    assert spec.implementation == ImplementationStatus.IMPLEMENTED


def test_registry_gl006_gl007_implemented():
    assert get_by_dict_code("GL-006") is not None
    assert get_by_dict_code("GL-007") is not None
    from rules.registry import ImplementationStatus

    assert get_by_dict_code("GL-006").implementation == ImplementationStatus.IMPLEMENTED
    assert get_by_dict_code("GL-007").implementation == ImplementationStatus.IMPLEMENTED


def test_registry_gl002_implemented():
    spec = get_by_dict_code("GL-002")
    assert spec is not None
    assert spec.rule_id == "rollforward_fa_list_reconciliation"
    from rules.registry import ImplementationStatus

    assert spec.implementation == ImplementationStatus.IMPLEMENTED


def test_registry_gl008_implemented():
    spec = get_by_dict_code("GL-008")
    assert spec is not None
    assert spec.rule_id == "rollforward_difference_over_sad"
    from rules.registry import ImplementationStatus

    assert spec.implementation == ImplementationStatus.IMPLEMENTED


def test_registry_gl004_implemented():
    spec = get_by_dict_code("GL-004")
    assert spec is not None
    assert spec.rule_id == "rollforward_depreciation_pl_reconciliation"
    from rules.registry import ImplementationStatus

    assert spec.implementation == ImplementationStatus.IMPLEMENTED


def test_rollforward_sheet_report_section():
    from ingest.models import RollforwardColumnBinding
    from report.rollforward_sheet_report import build_rollforward_sheet_section

    bindings = []
    for measure in ("original_value", "accumulated_depreciation", "impairment_provision", "net_value"):
        bindings.append(
            RollforwardColumnBinding(
                measure=measure,
                period_role=RollforwardPeriodRole.OPENING,
                column_index=3,
                source_header="审2",
            )
        )
        bindings.append(
            RollforwardColumnBinding(
                measure=measure,
                period_role=RollforwardPeriodRole.ENDING,
                column_index=8,
                source_header="审3",
            )
        )
    bindings.append(
        RollforwardColumnBinding(
            measure="original_value",
            period_role=RollforwardPeriodRole.MOVEMENT,
            column_index=12,
            source_header="原值变动金额",
        )
    )
    rf = _minimal_rf(
        amount_column_bindings=bindings,
        section_presence={
            "b1_bkd_main_table": True,
            "b4_table3_check_with_table1": True,
            "b5_table4_depreciation_pl": True,
        },
        table3_check_values=[Decimal("0")],
        table3_check_row=30,
        table4_difference=Decimal("0"),
        table4_difference_row=80,
        ending_totals={
            "impairment_provision": Decimal("0"),
            "original_value": Decimal("100"),
            "accumulated_depreciation": Decimal("20"),
            "net_value": Decimal("80"),
        },
        opening_totals={"original_value": Decimal("100")},
    )
    issues = attach_rule_metadata(run_rollforward_rules(rf))
    sec = build_rollforward_sheet_section(rf, issues)
    assert sec["ingested"] is True
    assert sec["rollforward_qc"]["overall_severity"] == "PASS"
