from __future__ import annotations

import re
from decimal import Decimal

from ingest.lead_sheet import LeadMovementRow, LeadSheetDataset
from rules.lead_common import (
    exceeds_volatility_threshold,
    is_affirmative,
    movement_amount_for_row,
    parse_threshold_amount,
)
from rules.models import QcIssue, Severity
from rules.parsing import is_blank

RULE_ID = "lead_fluctuation_notes_refs"

_INVESTIGATE_ROLES = ("investigate_quantitative", "investigate_qualitative")
_NOTE_PATTERNS = (
    re.compile(r"\b(?:note|nb|n)\s*[:#-]?\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"(?:注|说明|备注)\s*[:#-]?\s*(\d{1,3})"),
)


def _parse_percent(value: str | None) -> Decimal | None:
    if is_blank(value):
        return None
    text = str(value).strip().replace("%", "")
    try:
        val = Decimal(text)
    except Exception:
        return None
    if val > 1:
        val = val / Decimal("100")
    return val


def _note_refs(text: str | None) -> set[str]:
    if is_blank(text):
        return set()
    refs: set[str] = set()
    for pattern in _NOTE_PATTERNS:
        for match in pattern.finditer(str(text)):
            refs.add(str(int(match.group(1))))
    return refs


def _fallback_note_ref(text: str | None) -> set[str]:
    refs = _note_refs(text)
    if refs or is_blank(text):
        return refs
    stripped = str(text).strip()
    if re.fullmatch(r"\d{1,3}", stripped):
        return {str(int(stripped))}
    return refs


def _row_requires_note(
    row: LeadMovementRow,
    *,
    roles: set[str],
    vol_amount: Decimal | None,
    vol_percent: Decimal | None,
) -> bool:
    for role in _INVESTIGATE_ROLES:
        if role in roles and is_affirmative(row.values.get(role)):
            return True

    movement = movement_amount_for_row(row.values)
    movement_pct = _parse_percent(row.values.get("movement_pct"))
    if exceeds_volatility_threshold(
        movement,
        movement_pct,
        vol_amount=vol_amount,
        vol_percent=vol_percent,
    ):
        return True
    return False


def check_lead_fluctuation_notes_refs(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """Check that Lead main-table Notes references appear in the fluctuation notes block."""
    if lead is None or not lead.source_sheet or not lead.movement_rows:
        return []

    note_text = lead.fluctuation_notes or ""
    section_refs = _note_refs(note_text)
    roles = {b.role for b in lead.movement_bindings}
    vol_amount = parse_threshold_amount(lead.volatility.amount) if lead.volatility else None
    vol_percent = _parse_percent(lead.volatility.percent) if lead.volatility else None

    issues: list[QcIssue] = []
    main_refs: set[str] = set()
    missing_rows: list[LeadMovementRow] = []

    for row in lead.movement_rows:
        refs = _fallback_note_ref(row.values.get("notes"))
        main_refs.update(refs)
        requires_note = _row_requires_note(
            row,
            roles=roles,
            vol_amount=vol_amount,
            vol_percent=vol_percent,
        )
        if requires_note and not refs:
            missing_rows.append(row)
            continue
        missing_refs = refs - section_refs
        if missing_refs and note_text.strip():
            issues.append(
                QcIssue(
                    asset_id=None,
                    rule_id=RULE_ID,
                    field=f"notes:{row.account_label}",
                    severity=Severity.WARN,
                    message=(
                        f"Lead 主表「{row.account_label}」Notes 引用 "
                        f"{', '.join(sorted(missing_refs))}，但波动说明区未识别到对应编号"
                    ),
                    suggestion="在波动说明区补充对应 Notes 编号及分析，或修正主表 Notes 引用。",
                    procedure_code="K.00",
                    source_sheet=lead.source_sheet,
                    source_row=row.source_row,
                )
            )

    if missing_rows:
        labels = "、".join(r.account_label for r in missing_rows[:5])
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="movement_notes",
                severity=Severity.FAIL,
                message=f"Lead 主表存在需调查/超门槛行但未填写 Notes 引用：{labels}",
                suggestion="为需调查的主表行填写 Notes 编号，并在波动说明区展开说明。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=missing_rows[0].source_row,
            )
        )

    orphan_refs = section_refs - main_refs
    if orphan_refs and main_refs:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="fluctuation_notes",
                severity=Severity.NEED_REVIEW,
                message=(
                    "波动说明区存在未能在 Lead 主表 Notes 列反向匹配的编号："
                    f"{', '.join(sorted(orphan_refs))}"
                ),
                suggestion="复核波动说明编号是否与 Lead 主表行一致。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        )

    return issues
