"""K.01 后推规则单测。"""

from __future__ import annotations

from decimal import Decimal

from ingest.models import RollforwardLayoutProfile, RollforwardPeriodRole
from ingest.rollforward_sheet import RollforwardSheetDataset, parse_rollforward_rows
from rules.registry import attach_rule_metadata, get_by_dict_code
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
    )
    assert not check_rollforward_exists(rf)


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


def test_registry_gl006_gl007_implemented():
    assert get_by_dict_code("GL-006") is not None
    assert get_by_dict_code("GL-007") is not None
    from rules.registry import ImplementationStatus

    assert get_by_dict_code("GL-006").implementation == ImplementationStatus.IMPLEMENTED
    assert get_by_dict_code("GL-007").implementation == ImplementationStatus.IMPLEMENTED
