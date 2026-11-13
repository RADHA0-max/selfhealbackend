"""Conservative evidence gate for provisional synthetic signals."""

from dataclasses import replace

from agent.diagnosis import Diagnosis
from agent.signal_adapter import signal_to_evidence


def gate_diagnosis(signal: dict, diagnosis: Diagnosis) -> Diagnosis:
    """Downgrade unsupported root-cause claims; never execute actions."""

    evidence = signal_to_evidence(signal)
    probes = evidence["probes"]

    target = next(iter(probes))
    probe = probes[target]

    category = diagnosis.category

    expected_actions = {
        "api": "investigate_api",
        "auth": "investigate_auth",
        "worker": "investigate_worker",
        "database": "investigate_database",
    }

    action_consistent = (
        diagnosis.recommended_action == "collect_more_evidence"
        if category == "unknown"
        else diagnosis.recommended_action == (
            "investigate_latency"
            if category == "latency"
            else expected_actions[target]
        )
    )

    unsupported = (
        not action_consistent
        or (
            diagnosis.target != target
            or category in {"dependency_failure", "resource_exhaustion"}
        or (
            category == "latency"
            and "latency_ms" not in probe
            and probe["status"] not in {408, 504}
        )
        )
    )

    if not unsupported:
        return diagnosis

    return replace(
        diagnosis,
        category="unknown",
        target=target,
        confidence=0.0,
        summary="Insufficient evidence to establish the proposed failure category.",
        recommended_action="collect_more_evidence",
    )
