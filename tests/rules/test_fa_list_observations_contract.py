from ingest.models import (
    AssetRecord,
    FaListIdentityBasis,
    FaListIdentityScope,
    FaListSalvageBasis,
    FaListSalvageMode,
)
from rules.fa_list_observations import (
    build_asset_amount_non_negative_observation,
    build_salvage_rate_range_observation,
    build_unique_asset_id_observation,
)
from rules.models import ColumnContext


def test_amount_sign_observation_matches_actual_rule_contract():
    ctx = ColumnContext(
        mapped_fields={
            "asset_id",
            "original_value",
            "accumulated_depreciation",
            "impairment_provision",
            "net_value",
        },
        source_sheet="FA list",
    )
    observation = build_asset_amount_non_negative_observation(
        [AssetRecord(asset_id="A", original_value="100", accumulated_depreciation="-20", impairment_provision="-5", net_value="75")],
        ctx,
        [],
    )

    assert "原值和净值" in observation["check_logic"]
    assert "允许贷方负数" in observation["check_logic"]
    assert "同列不得混用" in observation["expected_result"]


def test_composite_identity_observation_describes_entity_asset_key():
    ctx = ColumnContext(
        mapped_fields={"entity_name", "asset_id"},
        source_sheet="FA list-汇总",
    )
    observation = build_unique_asset_id_observation(
        [AssetRecord(entity_name="A公司", asset_id="001")],
        ctx,
        [],
        FaListIdentityBasis(scope=FaListIdentityScope.ENTITY_ASSET_ID),
    )

    assert "实体与资产编号复合键" in observation["check_logic"]
    assert "相同编号跨实体" in observation["expected_result"]


def test_salvage_observation_exposes_dual_column_crosscheck_basis():
    ctx = ColumnContext(
        mapped_fields={"asset_id", "original_value", "salvage_value", "salvage_rate"},
        source_sheet="FA list",
    )
    basis = FaListSalvageBasis(
        mode=FaListSalvageMode.RATE_AND_VALUE,
        rate_column=29,
        value_column=10,
    )

    observation = build_salvage_rate_range_observation(
        [AssetRecord(source_row=11, asset_id="A", original_value="100", salvage_value="5", salvage_rate="5%")],
        ctx,
        [],
        basis,
    )

    assert "残值金额÷原值交叉验证" in observation["check_logic"]
    assert "rate_and_value" in observation["actual_result"]
    assert "残值率列 29" in observation["actual_result"]
    assert "残值金额列 10" in observation["actual_result"]
