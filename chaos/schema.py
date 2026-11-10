"""Strict validation for offline NanoClaw chaos scenarios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCENARIO_FILE = (
    Path(__file__).resolve().parents[1]
    / "selfhealbench"
    / "scenarios"
    / "pilot.json"
)

SERVICES = frozenset({"api", "db", "worker", "auth"})
FAULTS = frozenset({"error", "latency", "stop", "none"})
SEVERITIES = frozenset({"none", "medium", "high", "critical"})

SCENARIO_FIELDS = frozenset({
    "id",
    "name",
    "target",
    "fault",
    "expected_root",
    "expected_action",
    "severity",
})

OPTIONAL_FIELDS = frozenset({"delay_ms"})


class ChaosValidationError(ValueError):
    """Scenario is invalid or not in the approved fixture catalog."""


@dataclass(frozen=True)
class ChaosScenario:
    scenario_id: str
    name: str
    target: str
    fault: str
    expected_root: str
    expected_action: str
    severity: str
    delay_ms: int | None = None


def load_catalog(path: Path = SCENARIO_FILE) -> dict[str, dict[str, Any]]:
    """Load the repository's benchmark fixture catalog."""

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ChaosValidationError("catalog must be a list")

    catalog = {}

    for item in data:
        if not isinstance(item, dict):
            raise ChaosValidationError("catalog entry must be an object")

        scenario_id = item.get("id")

        if not isinstance(scenario_id, str):
            raise ChaosValidationError("invalid scenario ID")

        if scenario_id in catalog:
            raise ChaosValidationError("duplicate scenario ID")

        catalog[scenario_id] = item

    return catalog


def validate_scenario(
    raw: dict[str, Any],
    catalog: dict[str, dict[str, Any]] | None = None,
) -> ChaosScenario:
    """Validate against an exact, checked-in benchmark fixture."""

    if not isinstance(raw, dict):
        raise ChaosValidationError("scenario must be an object")

    if catalog is None:
        catalog = load_catalog()

    scenario_id = raw.get("id")

    if not isinstance(scenario_id, str):
        raise ChaosValidationError("invalid scenario ID")

    reference = catalog.get(scenario_id)

    if reference is None:
        raise ChaosValidationError("unknown scenario ID")

    expected_fields = SCENARIO_FIELDS | (
        {"delay_ms"} if "delay_ms" in reference else set()
    )

    if set(raw) != expected_fields:
        raise ChaosValidationError("unexpected scenario fields")

    if raw != reference:
        raise ChaosValidationError("scenario differs from benchmark fixture")

    target = raw["target"]
    fault = raw["fault"]
    severity = raw["severity"]

    if target not in SERVICES | {"none"}:
        raise ChaosValidationError("invalid target")

    if fault not in FAULTS:
        raise ChaosValidationError("invalid fault")

    if severity not in SEVERITIES:
        raise ChaosValidationError("invalid severity")

    if fault == "none":
        if target != "none":
            raise ChaosValidationError("healthy scenario requires target none")
    elif target not in SERVICES:
        raise ChaosValidationError("fault requires an allowlisted service")

    delay_ms = raw.get("delay_ms")

    if fault == "latency":
        if type(delay_ms) is not int or not 0 < delay_ms <= 5000:
            raise ChaosValidationError("invalid latency")
    elif delay_ms is not None:
        raise ChaosValidationError("delay only allowed for latency")

    return ChaosScenario(
        scenario_id=scenario_id,
        name=raw["name"],
        target=target,
        fault=fault,
        expected_root=raw["expected_root"],
        expected_action=raw["expected_action"],
        severity=severity,
        delay_ms=delay_ms,
    )
