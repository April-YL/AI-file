"""字段映射策略：按 sheet 类型限制可映射字段，避免 FA list 误映射程序列。"""

from __future__ import annotations

from ingest.models import SheetKind

# 某 sheet 类型上禁止映射的标准字段（其余 FIELD_SYNONYMS 仍可用）
DISALLOWED_FIELDS_BY_KIND: dict[SheetKind, frozenset[str]] = {
    SheetKind.FA_LIST: frozenset(
        {
            "addition_method",
            "disposal_date",
            "disposal_method",
            "current_depreciation",
        }
    ),
    SheetKind.ADDITION_LIST: frozenset({"disposal_date", "disposal_method"}),
    SheetKind.DEPRECIATION_TOD: frozenset({"addition_method", "disposal_date", "disposal_method"}),
    SheetKind.DEPRECIATION_TOD_SAMPLE: frozenset(
        {"addition_method", "disposal_date", "disposal_method"}
    ),
    SheetKind.ROLLFORWARD: frozenset(
        {
            "addition_method",
            "disposal_date",
            "disposal_method",
            "current_depreciation",
        }
    ),
    SheetKind.LEAD: frozenset(
        {
            "addition_method",
            "disposal_date",
            "disposal_method",
            "asset_id",
            "asset_name",
            "original_value",
            "accumulated_depreciation",
            "net_value",
        }
    ),
    SheetKind.SUMMARY: frozenset(
        {f for f in (
            "asset_id", "asset_name", "asset_category", "start_date",
            "useful_life_months", "salvage_rate", "original_value",
            "accumulated_depreciation", "impairment_provision", "net_value",
            "addition_method", "disposal_date", "disposal_method",
            "current_depreciation",
        )}
    ),
}

# 表头含下列片段时，勿将「使用寿命」等短同义词映射为 useful_life_months（多为日期列）
USEFUL_LIFE_HEADER_BLOCK_TOKENS = ("日期", "开始折", "资本开始", "资本化日期")

# 短同义词（<=3 字符）仅允许整表头精确匹配，避免「残值」误伤等
SHORT_SYNONYM_MAX_LEN = 3

# 仅特定 sheet 启用的额外同义词（避免 FA list 误映射「变动方式」等）
SHEET_FIELD_SYNONYM_EXTRAS: dict[SheetKind, dict[str, list[str]]] = {
    SheetKind.ADDITION_LIST: {
        "addition_method": ["变动方式", "取得方式", "资产来源", "新增类型"],
    },
}
