from __future__ import annotations

from rules.asset_value_consistency import check_asset_value_consistency
from rules.fa_list_required_fields import check_fa_list_required_fields
from ingest.models import AssetRecord
from rules.models import ColumnContext, QcIssue
from rules.unique_asset_id import check_unique_asset_id

FA_LIST_RULE_IDS = (
    "fa_list_required_fields",
    "unique_asset_id",
    "asset_value_consistency",
)


def run_fa_list_rules(
    records: list[AssetRecord],
    ctx: ColumnContext,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    issues.extend(check_fa_list_required_fields(records, ctx))
    issues.extend(check_unique_asset_id(records, ctx))
    issues.extend(check_asset_value_consistency(records, ctx))
    return issues
