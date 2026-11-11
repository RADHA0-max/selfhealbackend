"""Deterministic dry-run chaos planning with no execution capability."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from chaos.schema import (
    ChaosScenario,
    ChaosValidationError,
    load_catalog,
    validate_scenario,
)


@dataclass(frozen=True)
class ChaosPlan:
    plan_id: str
    scenario_id: str
    target: str
    fault: str
    parameters: dict[str, Any]
    mode: str
    executable: bool
    approval_status: str
    audit: dict[str, Any]


def plan_scenario(
    scenario_id: str,
    *,
    mode: str = "dry_run",
) -> ChaosPlan:
    """Create an offline plan; never inject a fault."""

    if mode != "dry_run":
        raise ChaosValidationError(
            "only dry_run mode is supported"
        )

    if not isinstance(scenario_id, str):
        raise ChaosValidationError("scenario ID must be a string")

    catalog = load_catalog()

    reference = catalog.get(scenario_id)

    if reference is None:
        raise ChaosValidationError("unknown scenario ID")

    scenario: ChaosScenario = validate_scenario(
        reference,
        catalog,
    )

    parameters = {}

    if scenario.delay_ms is not None:
        parameters["delay_ms"] = scenario.delay_ms

    canonical = json.dumps(
        {
            "scenario_id": scenario.scenario_id,
            "target": scenario.target,
            "fault": scenario.fault,
            "parameters": parameters,
            "mode": "dry_run",
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    plan_id = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:16]

    audit = {
        "event": "chaos_plan_created",
        "scenario_id": scenario.scenario_id,
        "plan_id": plan_id,
        "mode": "dry_run",
        "executed": False,
        "approval_status": "blocked",
        "reason": "live fault injection requires separate approval",
    }

    return ChaosPlan(
        plan_id=plan_id,
        scenario_id=scenario.scenario_id,
        target=scenario.target,
        fault=scenario.fault,
        parameters=parameters,
        mode="dry_run",
        executable=False,
        approval_status="blocked",
        audit=audit,
    )


def plan_to_dict(plan: ChaosPlan) -> dict[str, Any]:
    """Convert a plan into a JSON-compatible report."""

    if not isinstance(plan, ChaosPlan):
        raise TypeError("expected ChaosPlan")

    return asdict(plan)
