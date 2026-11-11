"""Strict offline signal-to-diagnosis evidence adapter.

Provisional Person C contract; not a runtime detector protocol.
"""

from __future__ import annotations

import re
from typing import Any


TARGETS = frozenset({"api", "auth", "worker", "database"})
SIGNAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


class SignalValidationError(ValueError):
    """Invalid synthetic signal."""


def signal_to_evidence(signal: dict[str, Any]) -> dict[str, Any]:
    """Validate a synthetic signal and produce diagnosis evidence."""

    if not isinstance(signal, dict):
        raise SignalValidationError("signal must be an object")

    required = {"signal_id", "target", "status"}
    optional = {"latency_ms"}

    if not required <= signal.keys() or signal.keys() - (required | optional):
        raise SignalValidationError("invalid signal fields")

    signal_id = signal["signal_id"]

    if not isinstance(signal_id, str) or not SIGNAL_ID.fullmatch(signal_id):
        raise SignalValidationError("invalid signal_id")

    target = signal["target"]

    if not isinstance(target, str) or target not in TARGETS:
        raise SignalValidationError("invalid target")

    status = signal["status"]

    if type(status) is not int or not 100 <= status <= 599:
        raise SignalValidationError("invalid HTTP status")

    probe = {"status": status}

    if "latency_ms" in signal:
        latency = signal["latency_ms"]

        if type(latency) is not int or not 0 <= latency <= 60000:
            raise SignalValidationError("invalid latency_ms")

        probe["latency_ms"] = latency

    return {
        "signal_id": signal_id,
        "probes": {
            target: probe,
        },
    }
