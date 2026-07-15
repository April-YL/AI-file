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
    SheetKind.DISPOSAL_LIST: frozenset(
        {"addition_method", "current_depreciation", "fully_depreciated_flag", "fully_depreciated_date"}
    ),
}

# 表头含下列片段时，勿将「使用寿命」等短同义词映射为 useful_life_months（多为日期列）
USEFUL_LIFE_HEADER_BLOCK_TOKENS = ("日期", "开始折", "资本开始", "资本化日期")

# 短同义词（<=3 字符）仅允许整表头精确匹配，避免「残值」误伤等
SHORT_SYNONYM_MAX_LEN = 3

# 仅特定 sheet 启用的额外同义词（避免 FA list 误映射「变动方式」等）
SHEET_FIELD_SYNONYM_EXTRAS: dict[SheetKind, dict[str, list[str]]] = {
    SheetKind.FA_LIST: {
        "entity_name": ["公司", "公司名称", "主体", "主体名称", "企业名称", "法人实体", "账套名称", "Entity"],
        "currency": ["币种", "货币", "货币类型", "Currency"],
        "salvage_value": ["净残值", "预计净残值", "残值金额", "预计残值金额", "预计净残值金额"],
    },
    SheetKind.ADDITION_LIST: {
        "addition_method": ["变动方式", "取得方式", "资产来源", "新增类型"],
        "original_value": [
            "新增原值",
            "本期新增原值",
            "本期新增金额",
            "新增金额",
            "期末原值",
            "原值本币",
            "原值原币",
            "购进原值",
        ],
    },
    SheetKind.DISPOSAL_LIST: {
        "original_value": [
            "处置原值",
            "原值本币",
            "原值原币",
            "减少原值",
            "本期减少原值",
        ],
        "accumulated_depreciation": [
            "处置累计折旧",
            "减少累计折旧",
            "本期减少累计折旧",
        ],
        "net_value": ["处置净值", "减少净值", "本期减少净值", "账面净值"],
        "disposal_date": ["业务日期", "凭证日期", "过账日期", "处置时间"],
        "disposal_method": [
            "变动方式",
            "处置类别",
            "减少类别",
            "处置类型",
            "报废类型",
            "减少类型",
            "新增/处置",
        ],
    },
}

# 按 sheet 类型屏蔽特定“表头 -> 标准字段”的组合。新增清单里“期初原值”
# 反映年初/切换日余额，不代表本期新增金额。
BLOCKED_HEADER_FIELD_BY_KIND: dict[SheetKind, dict[str, frozenset[str]]] = {
    SheetKind.ADDITION_LIST: {
        "original_value": frozenset({"期初原值", "年初原值", "上期原值"}),
    },
    SheetKind.DISPOSAL_LIST: {
        "original_value": frozenset({"期初原值", "年初原值", "上期原值", "期末原值", "2025年末原值"}),
        "accumulated_depreciation": frozenset(
            {"期初累计折旧", "年初累计折旧", "2025年末累计折旧"}
        ),
        "net_value": frozenset({"期初净值", "2025年末净值"}),
    },
}

# 同一标准字段出现多个候选列时，按表头业务含义选择更适合该 sheet 的列。
SHEET_FIELD_HEADER_PRIORITIES: dict[SheetKind, dict[str, tuple[str, ...]]] = {
    SheetKind.ADDITION_LIST: {
        "original_value": (
            "新增原值",
            "本期新增原值",
            "本期新增金额",
            "新增金额",
            "期末原值",
            "原值本币",
            "原值原币",
            "购进原值",
            "原值",
        ),
    },
    SheetKind.DISPOSAL_LIST: {
        "original_value": (
            "处置原值",
            "减少原值",
            "本期减少原值",
            "原值本币",
            "原值原币",
            "原值",
        ),
        "accumulated_depreciation": (
            "处置累计折旧",
            "减少累计折旧",
            "本期减少累计折旧",
            "累计折旧",
        ),
        "net_value": ("处置净值", "减少净值", "本期减少净值", "净值", "账面净值"),
        "disposal_date": ("处置日期", "处置时间", "业务日期", "减少日期", "报废日期", "凭证日期"),
        "disposal_method": (
            "减少方式",
            "处置/报废",
            "处置方式",
            "处置情况",
            "变动方式",
            "处置类别",
            "减少类别",
            "新增/处置",
        ),
    },
}
