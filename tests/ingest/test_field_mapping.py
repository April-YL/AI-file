import json
from pathlib import Path

import pytest

from ingest.field_mapping import check_required_fields, map_headers, match_standard_field
from ingest.models import FieldMapping, SheetKind

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
