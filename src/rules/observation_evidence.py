from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_EVIDENCE_ITEMS = 8
MAX_IDENTIFIED_TERMS = 12
MAX_KEY_COLUMNS = 12
MAX_VALUES_READ = 20
MAX_MISSING_DATA = 12
MAX_INPUTS = 8
MAX_CHECKS = 8
MAX_NOTES = 5


@dataclass(frozen=True)
class ObservationNormalizationResult:
    observation: dict[str, Any] | None
    truncations: tuple[str, ...] = ()


def normalize_observation_for_ledger(
    observation: dict[str, Any] | None,
) -> ObservationNormalizationResult:
    if observation is None or not isinstance(observation, dict):
        return ObservationNormalizationResult(observation)
    normalized = dict(observation)
    truncations: list[str] = []
    if set(normalized) == {"path", "inputs", "checks", "notes"}:
        normalized["inputs"] = _sample_sequence(normalized.get("inputs"), MAX_INPUTS, "inputs", truncations)
        normalized["checks"] = _sample_sequence(normalized.get("checks"), MAX_CHECKS, "checks", truncations)
        normalized["notes"] = _sample_sequence(normalized.get("notes"), MAX_NOTES, "notes", truncations)
        return ObservationNormalizationResult(normalized, tuple(truncations))
    checked_data = normalized.get("checked_data")
    if not isinstance(checked_data, list):
        return ObservationNormalizationResult(normalized)

    normalized["checked_data"] = [
        dict(item) if isinstance(item, dict) else item
        for item in _sample_sequence(
        checked_data, MAX_EVIDENCE_ITEMS, "checked_data", truncations
        )
    ]
    for index, item in enumerate(normalized["checked_data"]):
        if not isinstance(item, dict):
            continue
        item["key_columns"] = _stable_unique_sample(
            item.get("key_columns"), MAX_KEY_COLUMNS, f"checked_data[{index}].key_columns", truncations
        )
        item["values_read"] = _sample_sequence(
            item.get("values_read"), MAX_VALUES_READ, f"checked_data[{index}].values_read", truncations
        )
        item["missing_data"] = _stable_unique_sample(
            item.get("missing_data"), MAX_MISSING_DATA, f"checked_data[{index}].missing_data", truncations
        )
        identified = item.get("identified_by")
        if not isinstance(identified, dict):
            continue
        identified = dict(identified)
        item["identified_by"] = identified
        identified["matched_keywords"] = _stable_unique_sample(
            identified.get("matched_keywords"), MAX_IDENTIFIED_TERMS,
            f"checked_data[{index}].matched_keywords", truncations,
        )
        identified["matched_rows"] = _stable_unique_sample(
            identified.get("matched_rows"), MAX_IDENTIFIED_TERMS,
            f"checked_data[{index}].matched_rows", truncations, spread=True,
        )
        identified["matched_columns"] = _stable_unique_sample(
            identified.get("matched_columns"), MAX_IDENTIFIED_TERMS,
            f"checked_data[{index}].matched_columns", truncations,
        )

    if truncations:
        suffix = "证据摘要已压缩（" + "；".join(truncations) + "）；完整 findings 未截断。"
        existing = str(normalized.get("result_summary") or "").strip()
        prefix_limit = max(0, 500 - len(suffix) - (1 if existing else 0))
        normalized["result_summary"] = (
            f"{existing[:prefix_limit]} {suffix}" if existing else suffix[:500]
        )
    return ObservationNormalizationResult(normalized, tuple(truncations))


def _stable_unique_sample(
    values: Any,
    limit: int,
    label: str,
    truncations: list[str],
    *,
    spread: bool = False,
) -> Any:
    if not isinstance(values, list):
        return values
    unique: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = repr(value)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(value)
    return _sample_sequence(unique, limit, label, truncations, spread=spread)


def _sample_sequence(
    values: Any,
    limit: int,
    label: str,
    truncations: list[str],
    *,
    spread: bool = False,
) -> Any:
    if not isinstance(values, list) or len(values) <= limit:
        return values
    truncations.append(f"{label} {len(values)}→{limit}")
    if spread and limit >= 2:
        head = limit // 2
        return [*values[:head], *values[-(limit - head):]]
    return values[:limit]
