"""Validated synthetic signal diagnosis entry point.

Advisory only. No mitigation or external I/O beyond the injected RPC.
"""

from __future__ import annotations

from typing import Any

from agent.diagnosis import Diagnosis, RPCTransport, diagnose
from agent.signal_adapter import signal_to_evidence
from agent.evidence_gate import gate_diagnosis


def diagnose_signal(
    rpc: RPCTransport,
    signal: dict[str, Any],
) -> Diagnosis:
    """Validate the signal before invoking the diagnosis RPC."""
    evidence = signal_to_evidence(signal)
    diagnosis = diagnose(rpc, evidence)
    return gate_diagnosis(signal, diagnosis)
