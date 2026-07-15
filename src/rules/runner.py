from __future__ import annotations

from ingest.models import (
    AmountCurrencyRole,
    AmountPeriodRole,
    AssetRecord,
    FaListAmountBasis,
    FaListAmountBasisStatus,
    FaListIdentityScope,
    FaListPopulationStatus,
    FaListReviewProfile,
    FaListRoutingStatus,
    FaListSalvageMode,
)
from rules.asset_amount_non_negative import check_asset_amount_non_negative
from rules.asset_value_consistency import check_asset_value_consistency
from rules.execution_recorder import RuleExecutionRecorder
from rules.fa_list_observations import (
    build_asset_amount_non_negative_observation,
    build_asset_value_consistency_observation,
    build_profile_data_insufficient_observation,
    build_required_fields_observation,
    build_salvage_rate_range_observation,
    build_unique_asset_id_observation,
    build_useful_life_positive_observation,
)
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
    amount_basis: FaListAmountBasis | None = None,
    profile: FaListReviewProfile | None = None,
) -> list[QcIssue]:
    recorder = recorder or RuleExecutionRecorder()
    issues: list[QcIssue] = []
    amount_basis = profile.amount_basis if profile is not None else amount_basis

    required_records = list(records)
    if profile is not None:
        known_rows = {record.source_row for record in required_records}
        required_records.extend(
            record
            for record in profile.population.identity_incomplete_records
            if record.source_row not in known_rows
        )

    base_blockers = _base_profile_blockers(profile)
    if profile is not None and profile.population.status == FaListPopulationStatus.EMPTY:
        required_issues = recorder.execute_rule(
            "fa_list_required_fields",
            check_fa_list_required_fields,
            required_records,
            ctx,
            amount_basis,
            profile,
        )
        recorder.record_observation(
            "fa_list_required_fields",
            build_required_fields_observation(required_records, ctx, required_issues, profile),
        )
        issues.extend(required_issues)
        for rule_id in FA_LIST_RULE_IDS[1:]:
            _record_data_insufficient(recorder, rule_id, ctx, profile, base_blockers)
        return attach_rule_metadata(issues)

    required_issues = recorder.execute_rule(
        "fa_list_required_fields",
        check_fa_list_required_fields,
        required_records,
        ctx,
        amount_basis,
        profile,
    )
    recorder.record_observation(
        "fa_list_required_fields",
        build_required_fields_observation(required_records, ctx, required_issues, profile),
    )
    issues.extend(required_issues)

    identity_blockers = list(base_blockers)
    if profile is not None and profile.identity_basis.scope == FaListIdentityScope.UNRESOLVED:
        identity_blockers.extend(profile.identity_basis.conflicts or ["identity key is unresolved"])
    if identity_blockers:
        _record_data_insufficient(recorder, "unique_asset_id", ctx, profile, identity_blockers)
    else:
        unique_issues = recorder.execute_rule(
            "unique_asset_id",
            check_unique_asset_id,
            records,
            ctx,
            profile.identity_basis if profile else None,
        )
        recorder.record_observation(
            "unique_asset_id",
            build_unique_asset_id_observation(
                records,
                ctx,
                unique_issues,
                profile.identity_basis if profile else None,
            ),
        )
        issues.extend(unique_issues)

    amount_blockers = _amount_profile_blockers(profile, amount_basis)
    if amount_blockers:
        for rule_id in ("asset_amount_non_negative", "asset_value_consistency"):
            _record_data_insufficient(recorder, rule_id, ctx, profile, amount_blockers)
    else:
        amount_issues = recorder.execute_rule(
            "asset_amount_non_negative",
            check_asset_amount_non_negative,
            records,
            ctx,
        )
        recorder.record_observation(
            "asset_amount_non_negative",
            build_asset_amount_non_negative_observation(records, ctx, amount_issues),
        )
        issues.extend(amount_issues)
        value_issues = recorder.execute_rule(
            "asset_value_consistency",
            check_asset_value_consistency,
            records,
            ctx,
        )
        recorder.record_observation(
            "asset_value_consistency",
            build_asset_value_consistency_observation(records, ctx, value_issues),
        )
        issues.extend(value_issues)

    life_blockers = list(base_blockers)
    if "useful_life_months" not in ctx.mapped_fields:
        life_blockers.append("useful life column is missing")
    if life_blockers:
        _record_data_insufficient(recorder, "useful_life_positive", ctx, profile, life_blockers)
    else:
        life_issues = recorder.execute_rule(
            "useful_life_positive",
            check_useful_life_positive,
            records,
            ctx,
        )
        recorder.record_observation(
            "useful_life_positive",
            build_useful_life_positive_observation(records, ctx, life_issues),
        )
        issues.extend(life_issues)

    salvage_blockers = _salvage_profile_blockers(profile, ctx)
    if salvage_blockers:
        _record_data_insufficient(recorder, "salvage_rate_range", ctx, profile, salvage_blockers)
    else:
        salvage_issues = recorder.execute_rule(
            "salvage_rate_range",
            check_salvage_rate_range,
            records,
            ctx,
            profile.salvage_basis if profile else None,
        )
        recorder.record_observation(
            "salvage_rate_range",
            build_salvage_rate_range_observation(
                records,
                ctx,
                salvage_issues,
                profile.salvage_basis if profile else None,
            ),
        )
        issues.extend(salvage_issues)

    return attach_rule_metadata(issues)


def _base_profile_blockers(profile: FaListReviewProfile | None) -> list[str]:
    if profile is None:
        return []
    blockers: list[str] = []
    if profile.routing.status != FaListRoutingStatus.CONFIRMED:
        blockers.append(profile.routing.reason or "FA list route is unresolved")
    if profile.population.status != FaListPopulationStatus.READY:
        blockers.extend(profile.population.reasons or ["FA list population is unresolved"])
    return blockers


def _amount_profile_blockers(
    profile: FaListReviewProfile | None,
    amount_basis: FaListAmountBasis | None,
) -> list[str]:
    blockers = _base_profile_blockers(profile)
    required = {
        "original_value",
        "accumulated_depreciation",
        "impairment_provision",
        "net_value",
    }
    if amount_basis is None or amount_basis.status != FaListAmountBasisStatus.CONFIRMED:
        blockers.extend((amount_basis.conflicts if amount_basis else []) or ["amount basis is unresolved"])
    elif not required.issubset(amount_basis.bindings):
        blockers.append("complete original/depreciation/impairment/net amount group is unavailable")
    elif amount_basis.data_start_row is None or amount_basis.data_end_row is None:
        blockers.append("amount detail range is unbounded")
    elif amount_basis.period_role != AmountPeriodRole.ENDING:
        blockers.append("ending-period amount semantics are not confirmed")
    elif amount_basis.currency_role == AmountCurrencyRole.UNKNOWN:
        blockers.append("amount currency semantics are not confirmed")
    return blockers


def _salvage_profile_blockers(
    profile: FaListReviewProfile | None,
    ctx: ColumnContext,
) -> list[str]:
    blockers = _base_profile_blockers(profile)
    if profile is None:
        if "salvage_rate" not in ctx.mapped_fields:
            blockers.append("salvage rate column is missing")
        return blockers
    basis = profile.salvage_basis
    if basis.mode in {FaListSalvageMode.UNRESOLVED, FaListSalvageMode.MISSING}:
        blockers.extend(basis.conflicts or ["salvage basis is unresolved"])
    elif basis.mode == FaListSalvageMode.DERIVED_FROM_VALUE and "original_value" not in ctx.mapped_fields:
        blockers.append("original value is unavailable for salvage-rate derivation")
    return blockers


def _record_data_insufficient(
    recorder: RuleExecutionRecorder,
    rule_id: str,
    ctx: ColumnContext,
    profile: FaListReviewProfile | None,
    reasons: list[str],
) -> None:
    clean_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    recorder.record_data_insufficient(
        rule_id,
        "; ".join(clean_reasons) or "FA list input contract is unresolved",
    )
    recorder.record_observation(
        rule_id,
        build_profile_data_insufficient_observation(
            ctx,
            profile,
            rule_name=rule_id,
            reasons=clean_reasons,
        ),
    )
