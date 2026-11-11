"""Validated synthetic signal diagnosis entry point.

Advisory only. No mitigation or external I/O beyond the injected RPC.
"""

from __future__ import annotations

from typing import Any

from agent.diagnosis import Diagnosis, RPCTransport, diagnose
from agent.signal_adapter import signal_to_evidence


def diagnose_signal(
    rpc: RPCTransport,
    signal: dict[str, Any],
) -> Diagnosis:
    """Validate the signal before invoking the diagnosis RPC."""
    evidence = signal_to_evidence(signal)
    return diagnose(rpc, evidence)
