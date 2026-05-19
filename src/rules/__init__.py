"""固定资产质检规则。"""

from ingest.models import AssetRecord
from rules.models import AutomationLevel, ColumnContext, QcIssue, Severity
from rules.registry import (
    RuleSpec,
    attach_rule_metadata,
    get_by_dict_code,
    get_by_rule_id,
    iter_implemented,
)
from rules.runner import FA_LIST_RULE_IDS, run_fa_list_rules

__all__ = [
    "AssetRecord",
    "AutomationLevel",
    "ColumnContext",
    "QcIssue",
    "Severity",
    "RuleSpec",
    "FA_LIST_RULE_IDS",
    "run_fa_list_rules",
    "attach_rule_metadata",
    "get_by_dict_code",
    "get_by_rule_id",
    "iter_implemented",
]
