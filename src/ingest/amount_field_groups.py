from __future__ import annotations

import re
from collections import defaultdict

from ingest.field_mapping import match_standard_field
from ingest.models import (
    AmountBusinessRole,
    AmountColumnCandidate,
    AmountCurrencyRole,
    AmountFieldGroup,
    AmountGroupStatus,
    AmountPeriodRole,
    SheetKind,
)

AMOUNT_MEASURES = (
    "original_value",
    "accumulated_depreciation",
    "impairment_provision",
    "net_value",
)


def build_amount_field_groups(
    header_cells: list[tuple[int, str]],
    *,
    sheet_kind: SheetKind,
) -> list[AmountFieldGroup]:
    candidates = _candidates(header_cells, sheet_kind)
    if not candidates:
        return []

    candidates = [_infer_unsuffixed_currency(item, candidates) for item in candidates]

    explicit_domain = any(
        item.business_role in {AmountBusinessRole.ADDITION, AmountBusinessRole.DISPOSAL}
        for item in candidates
    ) or _headers_have_business_semantics(header_cells, sheet_kind)
    grouped: dict[tuple[AmountPeriodRole, AmountCurrencyRole, AmountBusinessRole], list[AmountColumnCandidate]] = defaultdict(list)
    for item in candidates:
        key = (item.period_role, item.currency_role, item.business_role)
        grouped[key].append(item)

    groups: list[AmountFieldGroup] = []
    for index, (key, members) in enumerate(grouped.items(), start=1):
        period_role, currency_role, business_role = key
        selected = _one_per_measure(members)
        duplicate_measures = sorted(
            measure for measure in AMOUNT_MEASURES
            if sum(item.measure == measure for item in members) > 1
        )
        missing = [measure for measure in AMOUNT_MEASURES if measure not in selected]
        target_role = _target_business_role(sheet_kind)
        is_target = business_role == target_role
        if business_role == AmountBusinessRole.BALANCE and target_role != AmountBusinessRole.BALANCE:
            is_target = not explicit_domain
        if duplicate_measures and is_target:
            status = AmountGroupStatus.CONFLICTED
        else:
            status = AmountGroupStatus.CONFIRMED if not missing and is_target else AmountGroupStatus.INCOMPLETE
        confidence = 0.95 if status == AmountGroupStatus.CONFIRMED else (0.75 if is_target else 0.35)
        groups.append(
            AmountFieldGroup(
                group_id=f"{sheet_kind.value}:amount:{index}",
                members=selected,
                period_role=period_role,
                currency_role=currency_role,
                business_role=business_role,
                status=status,
                confidence=confidence,
                reasons=[
                    "amount columns share period/currency/business semantics",
                    *(
                        ["duplicate measures in the same semantic amount group: " + ", ".join(duplicate_measures)]
                        if duplicate_measures
                        else []
                    ),
                ],
                missing_measures=missing,
            )
        )

    groups.sort(key=lambda group: (_group_priority(group, sheet_kind), group.confidence), reverse=True)
    if len(groups) > 1 and groups[0].status == AmountGroupStatus.CONFIRMED:
        top = _group_priority(groups[0], sheet_kind)
        second = _group_priority(groups[1], sheet_kind)
        if top == second and groups[1].status == AmountGroupStatus.CONFIRMED:
            groups[0].status = AmountGroupStatus.AMBIGUOUS
            groups[0].reasons.append("multiple equally preferred complete amount groups")
    return groups


def select_amount_field_group(groups: list[AmountFieldGroup]) -> AmountFieldGroup | None:
    return groups[0] if groups else None


def _candidates(
    header_cells: list[tuple[int, str]], sheet_kind: SheetKind
) -> list[AmountColumnCandidate]:
    result: list[AmountColumnCandidate] = []
    for column_index, raw_header in header_cells:
        header = str(raw_header or "").strip()
        measure = match_standard_field(header, sheet_kind)
        if measure not in AMOUNT_MEASURES:
            continue
        period, business = _roles(header, sheet_kind)
        currency = _currency(header)
        result.append(
            AmountColumnCandidate(
                measure=measure,
                source_header=header,
                column_index=column_index,
                period_role=period,
                currency_role=currency,
                business_role=business,
                evidence=(header,),
            )
        )
    return result


def _roles(header: str, sheet_kind: SheetKind) -> tuple[AmountPeriodRole, AmountBusinessRole]:
    text = _norm(header)
    if any(token in text for token in ("期初", "年初", "上期末")):
        return AmountPeriodRole.OPENING, AmountBusinessRole.BALANCE
    if any(token in text for token in ("期末", "年末")):
        return AmountPeriodRole.ENDING, AmountBusinessRole.BALANCE
    if any(token in text for token in ("处置", "减少", "报废")):
        return AmountPeriodRole.CURRENT_PERIOD, AmountBusinessRole.DISPOSAL
    if any(token in text for token in ("新增", "购置", "增加")):
        return AmountPeriodRole.CURRENT_PERIOD, AmountBusinessRole.ADDITION
    return AmountPeriodRole.UNKNOWN, AmountBusinessRole.BALANCE


def _currency(header: str) -> AmountCurrencyRole:
    text = _norm(header)
    if any(token in text for token in ("cny", "人民币", "本币", "本位币")):
        return AmountCurrencyRole.REPORTING
    if any(token in text for token in ("原币", "外币", "交易币")):
        return AmountCurrencyRole.ORIGINAL
    return AmountCurrencyRole.UNKNOWN


def _infer_unsuffixed_currency(
    item: AmountColumnCandidate,
    candidates: list[AmountColumnCandidate],
) -> AmountColumnCandidate:
    if item.currency_role != AmountCurrencyRole.UNKNOWN:
        return item
    if any(
        peer.currency_role == AmountCurrencyRole.REPORTING
        and peer.period_role == item.period_role
        and peer.business_role == item.business_role
        for peer in candidates
    ):
        return AmountColumnCandidate(
            measure=item.measure,
            source_header=item.source_header,
            column_index=item.column_index,
            period_role=item.period_role,
            currency_role=AmountCurrencyRole.ORIGINAL,
            business_role=item.business_role,
            evidence=(*item.evidence, "unsuffixed peer of reporting-currency column"),
        )
    return item


def _one_per_measure(members: list[AmountColumnCandidate]) -> dict[str, AmountColumnCandidate]:
    selected: dict[str, AmountColumnCandidate] = {}
    for member in members:
        selected.setdefault(member.measure, member)
    return selected


def _target_business_role(sheet_kind: SheetKind) -> AmountBusinessRole:
    if sheet_kind == SheetKind.DISPOSAL_LIST:
        return AmountBusinessRole.DISPOSAL
    if sheet_kind == SheetKind.ADDITION_LIST:
        return AmountBusinessRole.ADDITION
    return AmountBusinessRole.BALANCE


def _headers_have_business_semantics(
    header_cells: list[tuple[int, str]],
    sheet_kind: SheetKind,
) -> bool:
    text = " ".join(_norm(header) for _column, header in header_cells)
    if sheet_kind == SheetKind.ADDITION_LIST:
        tokens = ("\u65b0\u589e", "\u8d2d\u7f6e", "\u8f6c\u5165", "\u8d44\u672c\u5316")
    elif sheet_kind == SheetKind.DISPOSAL_LIST:
        tokens = ("\u5904\u7f6e", "\u51cf\u5c11", "\u62a5\u5e9f", "\u51fa\u552e", "\u6838\u9500")
    else:
        return False
    return any(token in text for token in tokens)


def _group_priority(group: AmountFieldGroup, sheet_kind: SheetKind) -> int:
    target = _target_business_role(sheet_kind)
    score = 1000 if group.status == AmountGroupStatus.CONFIRMED else 0
    score += 100 if group.business_role == target else 0
    if group.business_role == AmountBusinessRole.BALANCE and target == AmountBusinessRole.BALANCE:
        score += 100
    if group.currency_role == AmountCurrencyRole.REPORTING:
        score += 20
    elif group.currency_role == AmountCurrencyRole.UNKNOWN:
        score += 10
    score += len(group.members)
    return score


def _norm(value: str) -> str:
    return re.sub(r"[\s_\-/]+", "", value).lower()
