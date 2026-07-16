from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BulkGuardConfig:
    minimum_population: int = 30
    minimum_findings: int = 20
    minimum_population_ratio: float = 0.60
    minimum_cluster_ratio: float = 0.80


def evaluate_bulk_anomaly_guard(
    report: Any,
    workbook_context: Any,
    *,
    config: BulkGuardConfig = BulkGuardConfig(),
) -> dict[str, Any]:
    """Identify unsafe delivery clusters without changing raw findings or ledger."""
    issues = list(getattr(report, "issues", []) or [])
    by_rule: dict[str, list[tuple[int, Any]]] = defaultdict(list)
    for index, issue in enumerate(issues):
        if getattr(getattr(issue, "severity", None), "value", None) == "FAIL":
            by_rule[str(issue.rule_id)].append((index, issue))

    clusters: list[dict[str, Any]] = []
    for rule_id, indexed in by_rule.items():
        dataset = _dataset_for_rule(workbook_context, rule_id)
        population = len(getattr(dataset, "records", []) or []) if dataset is not None else 0
        count = len(indexed)
        if population < config.minimum_population or count < config.minimum_findings:
            continue
        population_ratio = count / max(population, 1)
        if population_ratio < config.minimum_population_ratio:
            continue
        key_counts = Counter(
            (getattr(issue, "field", None), getattr(issue, "source_col", None))
            for _index, issue in indexed
        )
        (dominant_field, dominant_col), dominant_count = key_counts.most_common(1)[0]
        cluster_ratio = dominant_count / count
        if cluster_ratio < config.minimum_cluster_ratio:
            continue
        upstream_reasons = _upstream_uncertainty(dataset, dominant_field)
        if not upstream_reasons:
            continue
        clusters.append(
            {
                "rule_id": rule_id,
                "finding_count": count,
                "population_size": population,
                "population_ratio": round(population_ratio, 4),
                "dominant_field": dominant_field,
                "dominant_source_col": dominant_col,
                "cluster_ratio": round(cluster_ratio, 4),
                "source_sheet": getattr(indexed[0][1], "source_sheet", None),
                "held_issue_indexes": [index for index, _issue in indexed],
                "trigger_reasons": [
                    "large share of the effective population reported by one rule",
                    "findings are concentrated on one mapped field/column",
                    *upstream_reasons,
                ],
                "aggregate_review": (
                    "Bulk anomaly requires review before line-by-line external delivery; "
                    "raw findings and locations are retained in the system report."
                ),
            }
        )
    return {
        "disposition": "REVIEW_REQUIRED" if clusters else "NORMAL",
        "clusters": clusters,
        "raw_finding_count": len(issues),
        "held_finding_count": sum(len(item["held_issue_indexes"]) for item in clusters),
    }


def _dataset_for_rule(workbook_context: Any, rule_id: str):
    if rule_id.startswith("addition_"):
        return getattr(workbook_context, "addition_list", None)
    if rule_id.startswith("disposal_"):
        return getattr(workbook_context, "disposal_list", None)
    if rule_id.startswith("fa_list_") or rule_id in {
        "unique_asset_id",
        "asset_value_consistency",
        "asset_amount_non_negative",
        "useful_life_positive",
        "salvage_rate_range",
    }:
        return getattr(workbook_context, "fa_list", None)
    return None


def _upstream_uncertainty(dataset: Any, field_name: str | None) -> list[str]:
    if dataset is None:
        return []
    reasons: list[str] = []
    sheet_decision = getattr(dataset, "sheet_resolution", None)
    if sheet_decision is not None and getattr(sheet_decision.status, "value", None) != "RESOLVED":
        reasons.append("sheet identity is not deterministically resolved")
    decision = (getattr(dataset, "field_resolutions", {}) or {}).get(field_name or "")
    if decision is not None:
        evidence_count = len({item.evidence_type for item in decision.evidence})
        if evidence_count <= 2:
            reasons.append("field mapping has only the minimum independent evidence")
        if str(getattr(decision, "resolution_source", "")).startswith("llm"):
            reasons.append("field mapping was selected through identification fallback")
        if getattr(decision, "reorganization_count", 0):
            reasons.append("field mapping was locally reorganized")
    if getattr(dataset, "amount_group_reorganization_count", 0):
        reasons.append("amount group was selected through identification fallback")
    return reasons
