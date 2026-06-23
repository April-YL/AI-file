from __future__ import annotations

from ingest.models import AssetRecord
from rules.asset_amount_non_negative import check_asset_amount_non_negative
from rules.asset_value_consistency import check_asset_value_consistency
from rules.execution_recorder import RuleExecutionRecorder
from rules.fa_list_required_fields import check_fa_list_required_fields
from rules.models import ColumnContext, QcIssue
from rules.registry import attach_rule_metadata
from rules.salvage_rate_range import check_salvage_rate_range
from rules.unique_asset_id import check_unique_asset_id
from rules.useful_life_positive import check_useful_life_positive

FA_LIST_RULE_IDS = (
    "fa_list_required_fields",
    "unique_asset_id",
    "asset_value_consistency",
    "asset_amount_non_negative",
    "useful_life_positive",
    "salvage_rate_range",
)


def run_fa_list_rules(
    records: list[AssetRecord],
    ctx: ColumnContext,
    *,
    recorder: RuleExecutionRecorder | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues: list[QcIssue] = []
    issues.extend(recorder.execute_rule("fa_list_required_fields", check_fa_list_required_fields, records, ctx))
    issues.extend(recorder.execute_rule("unique_asset_id", check_unique_asset_id, records, ctx))
    issues.extend(recorder.execute_rule("asset_amount_non_negative", check_asset_amount_non_negative, records, ctx))
    issues.extend(recorder.execute_rule("asset_value_consistency", check_asset_value_consistency, records, ctx))
    issues.extend(recorder.execute_rule("useful_life_positive", check_useful_life_positive, records, ctx))
    issues.extend(recorder.execute_rule("salvage_rate_range", check_salvage_rate_range, records, ctx))
    return attach_rule_metadata(issues)
