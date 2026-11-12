"""Bounded synthetic-signal diagnosis through the existing file RPC.

Advisory only. No mitigation, retries, or detector integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.diagnosis import Diagnosis
from agent.rpc_client import RPCClient
from agent.signal_adapter import signal_to_evidence
from agent.diagnosis import diagnose


def diagnose_file_rpc(
    signal: dict[str, Any],
    in_dir: str | Path,
    out_dir: str | Path,
    *,
    timeout: float = 30.0,
) -> Diagnosis:
    """Validate before constructing the RPC client or publishing a request."""
    evidence = signal_to_evidence(signal)

    client = RPCClient(
        in_dir,
        out_dir,
        timeout=timeout,
    )

    return diagnose(client, evidence)
