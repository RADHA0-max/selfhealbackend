"""Deterministic, offline chaos and recovery timeline evaluation."""

from __future__ import annotations

from typing import Any


class TimelineError(ValueError):
    """Invalid or unsafe recovery timeline."""


MAX_EVENTS = 1000
MAX_DURATION_MS = 600_000
ALLOWED_TARGETS = frozenset({
    "api", "auth", "worker", "database",
})


def validate_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate a bounded, time-ordered sequence of probe observations."""

    if not isinstance(events, list) or not 2 <= len(events) <= MAX_EVENTS:
        raise TimelineError("timeline requires 2..1000 events")

    validated = []
    previous_time = -1
    target = None

    for event in events:
        if not isinstance(event, dict):
            raise TimelineError("event must be an object")

        if set(event) != {"time_ms", "target", "status", "latency_ms"}:
            raise TimelineError("unexpected event fields")

        time_ms = event["time_ms"]
        status = event["status"]
        latency_ms = event["latency_ms"]
        current_target = event["target"]

        if type(time_ms) is not int or not 0 <= time_ms <= MAX_DURATION_MS:
            raise TimelineError("invalid event timestamp")

        if time_ms <= previous_time:
            raise TimelineError("timestamps must increase strictly")

        if current_target not in ALLOWED_TARGETS:
            raise TimelineError("unsupported target")

        if target is not None and current_target != target:
            raise TimelineError("mixed targets are not supported")

        if type(status) is not int or not 100 <= status <= 599:
            raise TimelineError("invalid HTTP status")

        if type(latency_ms) is not int or not 0 <= latency_ms <= 60000:
            raise TimelineError("invalid latency")

        validated.append(dict(event))
        previous_time = time_ms
        target = current_target

    return validated


def evaluate_timeline(
    events: list[dict[str, Any]],
    *,
    required_healthy: int = 3,
    healthy_latency_ms: int = 1000,
) -> dict[str, Any]:
    """Evaluate observed recovery; never attribute causality to an agent."""

    validated = validate_timeline(events)

    if type(required_healthy) is not int or not 2 <= required_healthy <= 10:
        raise TimelineError("required_healthy must be 2..10")

    if (
        type(healthy_latency_ms) is not int
        or not 1 <= healthy_latency_ms <= 60000
    ):
        raise TimelineError("invalid healthy latency threshold")

    first = validated[0]
    baseline_healthy = (
        200 <= first["status"] < 400
        and first["latency_ms"] <= healthy_latency_ms
    )

    healthy_streak = 0
    first_recovery_ms = None
    regressions = 0
    previously_healthy = False

    for event in validated[1:]:
        healthy = (
            200 <= event["status"] < 400
            and event["latency_ms"] <= healthy_latency_ms
        )

        if healthy:
            healthy_streak += 1
            previously_healthy = True

            if healthy_streak == required_healthy and first_recovery_ms is None:
                first_recovery_ms = event["time_ms"]
        else:
            if previously_healthy:
                regressions += 1
            healthy_streak = 0
            previously_healthy = False

    if baseline_healthy:
        outcome = "INCONCLUSIVE"
    elif first_recovery_ms is None:
        outcome = "FAILED"
    elif healthy_streak < required_healthy:
        outcome = "FAILED"
    else:
        outcome = "SUCCESS"

    return {
        "schema_version": 1,
        "target": first["target"],
        "observation_count": len(validated),
        "duration_ms": validated[-1]["time_ms"] - first["time_ms"],
        "first_sustained_recovery_ms": first_recovery_ms,
        "regression_count": regressions,
        "observation_outcome": outcome,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
    }
