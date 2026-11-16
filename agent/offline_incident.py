"""Offline incident diagnosis and observation; never executes mitigations."""

from __future__ import annotations

from typing import Any

from agent.diagnosis import RPCTransport
from agent.recovery_verification import verify_recovery, verify_sustained_recovery
from agent.signal_diagnosis import diagnose_signal
from agent.signal_adapter import signal_to_evidence


def evaluate_offline_incident(
    rpc: RPCTransport,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate two observations without claiming mitigation causality."""

    # Reject invalid observations before contacting the model.
    signal_to_evidence(before)
    signal_to_evidence(after)

    if before["target"] != after["target"]:
        raise ValueError("incident targets differ")

    if before["signal_id"] == after["signal_id"]:
        raise ValueError("observations must have distinct IDs")

    # Check observations before spending an RPC request.
    observation = verify_recovery(before, after)

    diagnosis = diagnose_signal(rpc, before)

    return {
        "schema_version": 1,
        "incident_id": before["signal_id"],
        "target": before["target"],
        "diagnosis_category": diagnosis.category,
        "diagnosis_action": diagnosis.recommended_action,
        "observation_outcome": observation,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
    }



def evaluate_sustained_offline_incident(
    rpc: RPCTransport,
    before: dict[str, Any],
    observations: list[dict[str, Any]],
    required_healthy: int = 3,
) -> dict[str, Any]:
    """Diagnose once after validating the entire observation sequence.

    No mitigation execution or causal recovery attribution.
    """
    outcome = verify_sustained_recovery(
        before, observations, required_healthy
    )

    diagnosis = diagnose_signal(rpc, before)

    return {
        "schema_version": 1,
        "incident_id": before["signal_id"],
        "target": before["target"],
        "diagnosis_category": diagnosis.category,
        "diagnosis_action": diagnosis.recommended_action,
        "observation_outcome": outcome,
        "observations_checked": len(observations),
        "required_healthy": required_healthy,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
    }
