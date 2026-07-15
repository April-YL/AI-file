from __future__ import annotations

import re

from ingest.models import FaListRoutingDecision, FaListRoutingStatus

_SUMMARY_TOKENS = ("汇总", "合并", "consol", "consolidated")


def choose_fa_list_route(
    candidates: list[str],
    *,
    explicit_sheet: str | None = None,
) -> FaListRoutingDecision:
    unique_candidates = list(dict.fromkeys(name for name in candidates if name))
    if explicit_sheet:
        if explicit_sheet not in unique_candidates:
            return FaListRoutingDecision(
                status=FaListRoutingStatus.NOT_FOUND,
                candidates=unique_candidates,
                reason=f"explicit FA list sheet not found: {explicit_sheet}",
            )
        return FaListRoutingDecision(
            status=FaListRoutingStatus.CONFIRMED,
            selected_sheet=explicit_sheet,
            candidates=unique_candidates,
            reason="explicit FA list sheet",
        )
    if not unique_candidates:
        return FaListRoutingDecision(
            status=FaListRoutingStatus.NOT_FOUND,
            candidates=[],
            reason="no FA list candidate",
        )
    if len(unique_candidates) == 1:
        return FaListRoutingDecision(
            status=FaListRoutingStatus.CONFIRMED,
            selected_sheet=unique_candidates[0],
            candidates=unique_candidates,
            reason="single FA list candidate",
        )

    summary_candidates = [name for name in unique_candidates if _is_summary_name(name)]
    if len(summary_candidates) == 1:
        return FaListRoutingDecision(
            status=FaListRoutingStatus.CONFIRMED,
            selected_sheet=summary_candidates[0],
            candidates=unique_candidates,
            reason="unique consolidated FA list candidate",
        )
    reason = (
        "multiple consolidated FA list candidates"
        if len(summary_candidates) > 1
        else "multiple peer FA list candidates"
    )
    return FaListRoutingDecision(
        status=FaListRoutingStatus.AMBIGUOUS,
        selected_sheet=None,
        candidates=unique_candidates,
        reason=reason,
    )


def _is_summary_name(name: str) -> bool:
    normalized = re.sub(r"\s+", "", str(name)).lower()
    return any(token in normalized for token in _SUMMARY_TOKENS) or normalized in {
        "groupfalist",
        "falistgroup",
    }
