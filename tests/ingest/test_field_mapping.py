import json
from pathlib import Path

import pytest

from ingest.field_mapping import (
    check_required_fields,
    map_headers,
    match_standard_field,
    resolve_fields,
    resolved_mappings,
)
from ingest.models import AssetRecord, FieldMapping, ResolutionStatus, SheetKind
from ingest.records import FaListDataset, apply_verified_field_selections

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CASE_HEADERS = FIXTURES / "field_mapping_case_headers.json"


def test_fa_list_synonyms():
    assert match_standard_field("卡片编码", SheetKind.FA_LIST) == "asset_id"
    assert match_standard_field("资产净值", SheetKind.FA_LIST) == "net_value"
    assert match_standard_field("使用年限(月)", SheetKind.FA_LIST) == "useful_life_months"


def test_disposal_blocks_document_number():
    assert match_standard_field("单据编号", SheetKind.DISPOSAL_LIST) is None


def test_fa_list_blocks_program_columns():
    assert match_standard_field("增加方式", SheetKind.FA_LIST) is None
    assert match_standard_field("变动方式", SheetKind.FA_LIST) is None


def test_depreciation_tod_blocks_date_as_useful_life():
    assert (
        match_standard_field(
            "资本开始折旧的日期 （即使用寿命开始时间）",
            SheetKind.DEPRECIATION_TOD,
        )
        is None
    )


def test_addition_list_变动方式():
    assert match_standard_field("变动方式", SheetKind.ADDITION_LIST) == "addition_method"


def test_addition_list_取得方式():
    assert match_standard_field("取得方式", SheetKind.ADDITION_LIST) == "addition_method"


def test_addition_list_blocks_opening_original_value():
    assert match_standard_field("期初原值", SheetKind.ADDITION_LIST) is None


def test_addition_list_prefers_ending_original_value_over_opening():
    mapped, _ = map_headers(
        [
            (8, "期初原值"),
            (11, "期末原值"),
            (12, "新增方式"),
        ],
        SheetKind.ADDITION_LIST,
    )
    by_field = {m.standard_field: m for m in mapped}
    assert by_field["original_value"].source_header == "期末原值"
    assert by_field["original_value"].column_index == 11


def test_addition_list_prefers_added_original_value_over_original_currency():
    mapped, _ = map_headers(
        [
            (19, "原值原币"),
            (20, "原值本币"),
            (23, "期初原值"),
            (25, "新增原值"),
        ],
        SheetKind.ADDITION_LIST,
    )
    by_field = {m.standard_field: m for m in mapped}
    assert by_field["original_value"].source_header == "新增原值"
    assert by_field["original_value"].column_index == 25


def test_disposal_处置情况():
    assert match_standard_field("处置情况", SheetKind.DISPOSAL_LIST) == "disposal_method"


def test_fa_list_semantic_required_identity_only_name():
    mapped = [
        FieldMapping("asset_name", "资产名称", 1),
        FieldMapping("original_value", "原值", 2),
        FieldMapping("accumulated_depreciation", "累计折旧", 3),
        FieldMapping("net_value", "净值", 4),
    ]
    missing_req, missing_rec = check_required_fields(mapped, SheetKind.FA_LIST)
    assert "asset_id|asset_name" not in missing_req
    assert "original_value" not in missing_req


def test_fa_list_missing_core():
    mapped = [FieldMapping("asset_id", "编号", 1)]
    missing_req, _ = check_required_fields(mapped, SheetKind.FA_LIST)
    assert "original_value" in missing_req
    assert "net_value" in missing_req


@pytest.mark.parametrize(
    "header,sheet_kind,expect",
    [
        (c["header"], SheetKind(c["sheet_kind"]), c["expect"])
        for c in json.loads(CASE_HEADERS.read_text(encoding="utf-8"))["cases"]
    ],
    ids=lambda x: x if isinstance(x, str) else None,
)
def test_case_library_headers(header: str, sheet_kind: SheetKind, expect: str | None):
    assert match_standard_field(header, sheet_kind) == expect


def test_map_headers_dedupes_standard_field():
    cells = [
        (1, "固定资产编号"),
        (2, "资产编号"),
        (3, "原值"),
        (4, "累计折旧"),
        (5, "净值"),
    ]
    mapped, unmapped = map_headers(cells, SheetKind.FA_LIST)
    fields = {m.standard_field for m in mapped}
    assert "asset_id" in fields
    assert len([m for m in mapped if m.standard_field == "asset_id"]) == 1


def test_resolve_fields_prefers_month_life_over_year_life():
    decisions = resolve_fields(
        [(1, "资产编号"), (2, "使用年限(年)"), (3, "使用年限(月)")],
        SheetKind.FA_LIST,
        rows=[
            ("资产编号", "使用年限(年)", "使用年限(月)"),
            ("FA-TEST-001", 5, 60),
            ("FA-TEST-002", 10, 120),
        ],
        header_row=1,
        source_sheet="FA list",
    )

    decision = decisions["useful_life_months"]
    assert decision.status == ResolutionStatus.RESOLVED
    assert decision.selected_candidate.column_index == 3
    assert any(candidate.negative_evidence for candidate in decision.candidates if candidate.column_index == 2)


def test_resolve_fields_does_not_adopt_legacy_asset_id_by_name_alone():
    decisions = resolve_fields(
        [(1, "旧资产编号"), (2, "资产名称")],
        SheetKind.FA_LIST,
        rows=[("旧资产编号", "资产名称"), ("OLD-001", "设备")],
        header_row=1,
    )

    assert decisions["asset_id"].status == ResolutionStatus.INVALID
    assert "asset_id" not in {item.standard_field for item in resolved_mappings(decisions)}


def test_resolve_fields_rejects_unscaled_salvage_rate_five():
    decisions = resolve_fields(
        [(1, "资产编号"), (2, "残值率")],
        SheetKind.FA_LIST,
        rows=[("资产编号", "残值率"), ("FA-TEST-001", 5), ("FA-TEST-002", 5)],
        header_row=1,
        number_formats={2: ["0", "0"]},
    )

    assert decisions["salvage_rate"].status == ResolutionStatus.INVALID


def test_resolve_fields_keeps_equal_duplicate_candidates_ambiguous():
    decisions = resolve_fields(
        [(1, "资产编号"), (2, "资产编号")],
        SheetKind.ADDITION_LIST,
        rows=[("资产编号", "资产编号"), ("FA-TEST-001", "FA-TEST-101")],
        header_row=1,
    )

    assert decisions["asset_id"].status == ResolutionStatus.AMBIGUOUS


def test_verified_selection_reorganizes_affected_field_at_most_once(monkeypatch):
    decisions = resolve_fields(
        [(1, "资产编号"), (2, "资产编号")],
        SheetKind.FA_LIST,
        rows=[("资产编号", "资产编号"), ("OLD", "FA-TEST-001")],
        header_row=1,
    )
    dataset = FaListDataset(
        source_file="demo.xlsx",
        source_sheet="FA list",
        mapped_fields=[],
        records=[AssetRecord(source_row=2)],
        field_resolutions=decisions,
    )

    class Sheet:
        def cell(self, row, column):
            return type("Cell", (), {"value": "FA-TEST-001"})()

    class Workbook:
        sheetnames = ["FA list"]

        def __getitem__(self, name):
            return Sheet()

        def close(self):
            pass

    monkeypatch.setattr("ingest.records.openpyxl.load_workbook", lambda *args, **kwargs: Workbook())

    first = apply_verified_field_selections(
        dataset,
        workbook_path="demo.xlsx",
        selections={"asset_id": 2},
    )
    second = apply_verified_field_selections(
        dataset,
        workbook_path="demo.xlsx",
        selections={"asset_id": 1},
    )

    assert first == ["asset_id"]
    assert second == []
    assert dataset.records[0].asset_id == "FA-TEST-001"
    assert decisions["asset_id"].reorganization_count == 1
