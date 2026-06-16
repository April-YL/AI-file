from __future__ import annotations

from collections import defaultdict

from ingest.models import AssetRecord
from rules.addition_common import is_purchase_addition_method
from rules.models import ColumnContext, QcIssue, Severity
from rules.parsing import is_blank, record_is_empty_data_row

RULE_ID = "addition_population_homogeneity"
_SPECIAL_TERMS = (
    "企业合并",
    "合并增加",
    "调拨",
    "重分类",
    "存货",
    "投资性房地产",
    "投房",
    "划入",
    "其他",
)


def check_addition_population_homogeneity(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    """提示新增清单中非购置新增，供人工判断是否需单独分总体/设计程序。"""
    if "addition_method" not in ctx.mapped_fields:
        return []

    special_rows: dict[str, list[int]] = defaultdict(list)
    for record in records:
        if record_is_empty_data_row(record, ctx.mapped_fields):
            continue
        method = record.addition_method
        if is_blank(method):
            continue
        if is_purchase_addition_method(method):
            continue
        if _is_special_method(method):
            special_rows[str(method).strip()].append(record.source_row or 0)

    if not special_rows:
        return []

    fragments = []
    for method, rows in special_rows.items():
        sample_rows = [str(r) for r in rows[:5] if r]
        suffix = f"（示例行：{', '.join(sample_rows)}）" if sample_rows else ""
        fragments.append(f"{method}: {len(rows)} 行{suffix}")

    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field="addition_method",
            severity=Severity.NEED_REVIEW,
            message=(
                "新增清单存在非购置新增方式，可能不适合直接并入购置新增测试总体："
                + "；".join(fragments)
            ),
            suggestion=(
                "确认这些新增是否已单独分总体、索引至对应 PSP/OSP，或已设计额外程序；"
                "如为在建工程转入，关注是否已在在建工程底稿执行相关测试。"
            ),
            procedure_code=ctx.procedure_code,
            source_sheet=ctx.source_sheet,
        )
    ]


def _is_special_method(value: str) -> bool:
    text = str(value).strip().lower()
    return any(term in text for term in _SPECIAL_TERMS)
