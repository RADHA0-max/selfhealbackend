"""Strict advisory diagnosis boundary for validated probe evidence.

This is not a production detector adapter.
"""

from __future__ import annotations

import json
from typing import Any

from agent.diagnosis import Diagnosis, RPCTransport, diagnose
from agent.evidence_gate import gate_diagnosis
from agent.signal_adapter import signal_to_evidence


class EvidenceBoundaryError(ValueError):
    """Evidence is not supported by the provisional contract."""


def diagnose_evidence(
    rpc: RPCTransport,
    evidence: dict[str, Any],
) -> Diagnosis:
    """Validate evidence before RPC and apply the conservative gate."""

    if not isinstance(evidence, dict):
        raise EvidenceBoundaryError("evidence must be an object")

    try:
        payload = json.dumps(
            evidence,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise EvidenceBoundaryError("invalid evidence JSON") from exc

    if len(payload) > 16 * 1024:
        raise EvidenceBoundaryError("evidence exceeds 16 KiB")

    if set(evidence) != {"signal_id", "probes"}:
        raise EvidenceBoundaryError("unsupported evidence fields")

    probes = evidence["probes"]
    if not isinstance(probes, dict) or len(probes) != 1:
        raise EvidenceBoundaryError("exactly one probe required")

    target, probe = next(iter(probes.items()))
    if not isinstance(probe, dict):
        raise EvidenceBoundaryError("invalid probe")

    signal = {"signal_id": evidence["signal_id"], "target": target}
    signal.update(probe)

    try:
        canonical = signal_to_evidence(signal)
    except ValueError as exc:
        raise EvidenceBoundaryError("unsupported probe evidence") from exc

    if canonical != evidence:
        raise EvidenceBoundaryError("noncanonical evidence")

    result = diagnose(rpc, canonical)
    return gate_diagnosis(signal, result)
