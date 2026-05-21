from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    is_affirmative,
    is_trivial_fluctuation_note,
    movement_amount_for_row,
    parse_threshold_amount,
)
from rules.models import QcIssue, Severity
from rules.parsing import is_blank, parse_amount

RULE_ID = "unexpected_movement_investigation"

_INVESTIGATE_ROLES = ("investigate_quantitative", "investigate_qualitative")


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


def _exceeds_volatility(
    movement_amt: Decimal | None,
    movement_pct: Decimal | None,
    *,
    vol_amount: Decimal | None,
    vol_percent: Decimal | None,
) -> bool:
    if vol_amount is not None and movement_amt is not None:
        if abs(movement_amt) > vol_amount:
            return True
    if vol_percent is not None and movement_pct is not None:
        if abs(movement_pct) > vol_percent:
            return True
    return False


def check_unexpected_movement_investigation(lead: LeadSheetDataset | None) -> list[QcIssue]:
    """超波动门槛或调查=是时，波动说明不得为空或仅「无异常波动」。"""
    if lead is None or not lead.source_sheet or not lead.movement_rows:
        return []

    vol = lead.volatility
    vol_amt = parse_threshold_amount(vol.amount) if vol else None
    vol_pct = _parse_percent(vol.percent) if vol else None
    note_ok = not is_trivial_fluctuation_note(lead.fluctuation_notes)
    roles = {b.role for b in lead.movement_bindings}

    issues: list[QcIssue] = []
    triggers: list[str] = []

    for row in lead.movement_rows:
        mov = movement_amount_for_row(row.values)
        pct_raw = row.values.get("movement_pct")
        mov_pct = _parse_percent(pct_raw) if pct_raw else None
        if _exceeds_volatility(mov, mov_pct, vol_amount=vol_amt, vol_percent=vol_pct):
            triggers.append(f"{row.account_label}:超门槛")
        for role in _INVESTIGATE_ROLES:
            if role in roles and is_affirmative(row.values.get(role)):
                triggers.append(f"{row.account_label}:须调查")
                break

    if not triggers:
        return []

    if is_blank(lead.fluctuation_notes) or not note_ok:
        sev = Severity.FAIL if any("须调查" in t for t in triggers) else Severity.WARN
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="fluctuation_notes",
                severity=sev,
                message=(
                    "存在超波动门槛或须调查行，但波动说明为空或仅为「无异常波动」"
                    f"（{'; '.join(triggers[:5])}）"
                ),
                suggestion="在波动说明区补充分析，并确保 Notes 与主表一致",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
            )
        )
    return issues
