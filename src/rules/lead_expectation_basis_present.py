from __future__ import annotations

import re

from ingest.lead_sheet import LeadSheetDataset
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_expectation_basis_present"

_TRIVIAL_EXPECTATION_PATTERNS = (
    "无异常",
    "无重大",
    "无变化",
    "无波动",
    "合理",
    "正常",
    "不适用",
    "n/a",
    "na",
)


def _compact(text: str | None) -> str:
    return re.sub(r"[\s_\-，。,.;；:：()（）]", "", str(text or "").strip().lower())


def _looks_trivial(text: str | None) -> bool:
    if is_blank(text):
        return True
    compact = _compact(text)
    if len(compact) <= 4:
        return True
    return any(pattern in compact for pattern in _TRIVIAL_EXPECTATION_PATTERNS)


def check_lead_expectation_basis_present(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """Weak check: expectation rows should include some basis, not only a bare conclusion."""
    if lead is None or not lead.source_sheet or not lead.expectations:
        return []

    weak_rows = [row for row in lead.expectations if _looks_trivial(row.expectation)]
    if not weak_rows:
        return []

    if len(weak_rows) == len(lead.expectations):
        severity = Severity.WARN
        message = "Lead 预期分析均为空或仅为简短结论，未体现判断依据"
    else:
        severity = Severity.NEED_REVIEW
        message = "Lead 部分预期分析较简略，建议复核是否已说明判断依据"

    labels = "、".join(row.account_change for row in weak_rows[:5])
    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field="expectation_basis",
            severity=severity,
            message=f"{message}：{labels}",
            suggestion="补充预期形成依据，例如预算/业务计划、历史趋势、K.01/K.02/K.03 程序或具体金额口径。",
            procedure_code="K.00",
            source_sheet=lead.source_sheet,
            source_row=weak_rows[0].source_row,
        )
    ]
