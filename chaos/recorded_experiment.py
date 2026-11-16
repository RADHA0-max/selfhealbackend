"""Bounded offline evaluation of recorded probe experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chaos.recovery_timeline import TimelineError, evaluate_timeline


MAX_INPUT_BYTES = 1024 * 1024
MAX_SCENARIOS = 50
ALLOWED_KINDS = frozenset({
    "service_failure",
    "latency_spike",
    "intermittent_failure",
    "negative_control",
})


class ExperimentError(ValueError):
    """Invalid recorded experiment."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExperimentError("duplicate JSON key")
        result[key] = value
    return result


def load_experiment(path: str | Path) -> dict[str, Any]:
    """Load a bounded JSON experiment without executing any content."""
    source = Path(path)

    if source.is_symlink() or not source.is_file():
        raise ExperimentError("invalid experiment file")

    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ExperimentError("experiment file exceeds size limit")

    try:
        raw = source.read_bytes()
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ExperimentError("non-finite JSON value")
            ),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ExperimentError("invalid experiment JSON") from exc

    if not isinstance(data, dict) or set(data) != {
        "schema_version", "experiment_id", "scenarios"
    }:
        raise ExperimentError("invalid experiment schema")

    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ExperimentError("unsupported experiment version")

    identifier = data["experiment_id"]
    if (
        not isinstance(identifier, str)
        or not 1 <= len(identifier) <= 64
        or not all(char.isalnum() or char in "_-" for char in identifier)
    ):
        raise ExperimentError("invalid experiment ID")

    scenarios = data["scenarios"]
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= MAX_SCENARIOS:
        raise ExperimentError("invalid scenario count")

    seen = set()

    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {
            "scenario_id", "kind", "events"
        }:
            raise ExperimentError("invalid scenario schema")

        scenario_id = scenario["scenario_id"]
        if (
            not isinstance(scenario_id, str)
            or not 1 <= len(scenario_id) <= 64
            or not all(char.isalnum() or char in "_-" for char in scenario_id)
            or scenario_id in seen
        ):
            raise ExperimentError("invalid or duplicate scenario ID")

        seen.add(scenario_id)

        if scenario["kind"] not in ALLOWED_KINDS:
            raise ExperimentError("unsupported scenario kind")

    return data


def evaluate_experiment(
    data: dict[str, Any],
    *,
    required_healthy: int = 3,
    healthy_latency_ms: int = 1000,
) -> dict[str, Any]:
    """Evaluate all recorded scenarios without model calls or mitigation."""

    if not isinstance(data, dict):
        raise ExperimentError("invalid experiment")

    # Validate the same schema for in-memory and file-backed inputs.
    # Round-trip through the bounded parser rather than trusting callers.
    encoded = json.dumps(data, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        raise ExperimentError("experiment exceeds size limit")

    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        path = Path(directory) / "experiment.json"
        path.write_bytes(encoded)
        validated = load_experiment(path)

    results = []
    counts = {"SUCCESS": 0, "FAILED": 0, "INCONCLUSIVE": 0}

    for scenario in validated["scenarios"]:
        try:
            outcome = evaluate_timeline(
                scenario["events"],
                required_healthy=required_healthy,
                healthy_latency_ms=healthy_latency_ms,
            )
        except TimelineError as exc:
            raise ExperimentError(
                "invalid timeline for scenario " + scenario["scenario_id"]
            ) from exc

        if scenario["kind"] == "negative_control":
            # Healthy controls are not incidents and cannot count as recovery.
            if outcome["observation_outcome"] != "INCONCLUSIVE":
                raise ExperimentError("negative control unexpectedly recovered")

        counts[outcome["observation_outcome"]] += 1

        results.append({
            "scenario_id": scenario["scenario_id"],
            "kind": scenario["kind"],
            "timeline": outcome,
        })

    return {
        "report_version": 1,
        "experiment_id": validated["experiment_id"],
        "scenario_count": len(results),
        "outcome_counts": counts,
        "scenarios": results,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
    }
