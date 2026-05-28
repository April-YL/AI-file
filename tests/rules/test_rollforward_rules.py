"""K.01 后推规则单测。"""

from __future__ import annotations

from decimal import Decimal

from ingest.models import RollforwardLayoutProfile, RollforwardPeriodRole
from ingest.rollforward_sheet import RollforwardSheetDataset, parse_rollforward_rows
from rules.registry import attach_rule_metadata, get_by_dict_code
from rules.rollforward_abnormal_amounts import check_rollforward_abnormal_amounts
from rules.rollforward_columns_complete import check_rollforward_columns_complete
from rules.rollforward_exists import check_rollforward_exists
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
        section_presence={"b1_bkd_main_table": True},
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
