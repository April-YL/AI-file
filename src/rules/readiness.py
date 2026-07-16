from __future__ import annotations

from dataclasses import dataclass, field

from ingest.models import ResolutionStatus
from rules.models import ColumnContext, ReadinessStatus, RuleExecutionMode


@dataclass(frozen=True)
class RuleReadinessSpec:
    rule_id: str
    execution_mode: RuleExecutionMode = RuleExecutionMode.DETERMINISTIC
    required_data: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    required_sheet_kind: str | None = None
    required_semantics: tuple[str, ...] = ()
    minimum_evidence: int = 0
    allowed_llm_capability: str | None = None
    insufficient_action: str = "DATA_INSUFFICIENT"
    block_on_missing: bool = True


@dataclass
class ReadinessDecision:
    rule_id: str
    status: ReadinessStatus
    blocking_fields: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == ReadinessStatus.READY

    def note(self) -> str:
        details = "; ".join(dict.fromkeys(self.reasons))
        fields = ", ".join(dict.fromkeys(self.blocking_fields))
        if fields and details:
            return f"blocking fields: {fields}; {details}"
        return details or (f"blocking fields: {fields}" if fields else self.status.value)


def readiness_spec_from_registry(spec) -> RuleReadinessSpec:
    return RuleReadinessSpec(
        rule_id=spec.rule_id,
        execution_mode=spec.execution_mode,
        required_data=spec.required_data,
        required_fields=spec.required_fields,
        required_sheet_kind=spec.required_sheet_kind,
        required_semantics=spec.required_semantics,
        minimum_evidence=spec.minimum_evidence,
        allowed_llm_capability=spec.allowed_llm_capability,
        insufficient_action=spec.insufficient_action,
        block_on_missing=spec.block_on_missing,
    )


def evaluate_rule_readiness(
    spec: RuleReadinessSpec,
    ctx: ColumnContext | None,
    *,
    data_available: bool = True,
    applicable: bool = True,
) -> ReadinessDecision:
    if not applicable:
        return ReadinessDecision(
            spec.rule_id,
            ReadinessStatus.NOT_APPLICABLE,
            reasons=["rule is not applicable to the identified execution path"],
        )
    if not data_available or ctx is None:
        return ReadinessDecision(
            spec.rule_id,
            ReadinessStatus.DATA_INSUFFICIENT,
            reasons=["required dataset or column context is unavailable"],
        )

    missing_data = [item for item in spec.required_data if item not in ctx.available_data]
    if missing_data:
        return ReadinessDecision(
            spec.rule_id,
            ReadinessStatus.DATA_INSUFFICIENT,
            reasons=["required data is unavailable: " + ", ".join(missing_data)],
        )
    if spec.required_sheet_kind and (
        ctx.sheet_resolution_status != "RESOLVED"
        or ctx.sheet_kind != spec.required_sheet_kind
    ):
        return ReadinessDecision(
            spec.rule_id,
            ReadinessStatus.DATA_INSUFFICIENT,
            reasons=[
                "required sheet identity is not confirmed: "
                f"expected {spec.required_sheet_kind}, got "
                f"{ctx.sheet_kind}/{ctx.sheet_resolution_status}"
            ],
        )
    if not ctx.derivatives_current:
        return ReadinessDecision(
            spec.rule_id,
            ReadinessStatus.DATA_INSUFFICIENT,
            reasons=["derived list profiles or summaries are stale"],
        )
    missing_semantics = [
        item
        for item in spec.required_semantics
        if ctx.semantic_states.get(item) != "CONFIRMED"
    ]
    if missing_semantics:
        return ReadinessDecision(
            spec.rule_id,
            ReadinessStatus.DATA_INSUFFICIENT,
            reasons=[
                "required business semantics are not confirmed: "
                + ", ".join(missing_semantics)
            ],
        )

    blocking_fields: list[str] = []
    reasons: list[str] = []
    for field_name in spec.required_fields:
        decision = ctx.field_resolutions.get(field_name)
        if decision is None:
            if field_name not in ctx.mapped_fields and spec.block_on_missing:
                blocking_fields.append(field_name)
                reasons.append(f"{field_name}: field is missing")
            continue
        if decision.status in {ResolutionStatus.AMBIGUOUS, ResolutionStatus.INVALID}:
            blocking_fields.append(field_name)
            reasons.append(f"{field_name}: resolution is {decision.status.value}")
            reasons.extend(decision.rejection_reasons)
            continue
        if decision.status == ResolutionStatus.MISSING:
            if spec.block_on_missing:
                blocking_fields.append(field_name)
                reasons.append(f"{field_name}: field is missing")
            continue
        if decision.status != ResolutionStatus.RESOLVED:
            blocking_fields.append(field_name)
            reasons.append(f"{field_name}: field is not resolved")
            continue
        evidence_count = len({item.evidence_type for item in decision.evidence})
        if evidence_count < spec.minimum_evidence:
            blocking_fields.append(field_name)
            reasons.append(
                f"{field_name}: {evidence_count} evidence types, minimum {spec.minimum_evidence}"
            )

    if blocking_fields:
        return ReadinessDecision(
            spec.rule_id,
            ReadinessStatus.DATA_INSUFFICIENT,
            blocking_fields=blocking_fields,
            reasons=reasons,
        )
    return ReadinessDecision(spec.rule_id, ReadinessStatus.READY)


def record_readiness_failure(recorder, decision: ReadinessDecision) -> None:
    if decision.status == ReadinessStatus.DATA_INSUFFICIENT:
        recorder.record_data_insufficient(decision.rule_id, decision.note())
    elif decision.status == ReadinessStatus.NOT_APPLICABLE:
        recorder.record_not_applicable(decision.rule_id, decision.note())
