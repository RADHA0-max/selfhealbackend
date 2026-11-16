"""Bounded startup-configured faults for the isolated NanoClaw testbed."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


ALLOWED_MODES = frozenset({
    "healthy",
    "outage",
    "latency",
    "timeout_response",
    "intermittent",
    "recovering",
    "regression",
})

LATENCY_SECONDS = 0.25


class FaultConfigurationError(ValueError):
    """Invalid testbed fault configuration."""


@dataclass(frozen=True)
class FaultObservation:
    status: int
    delay_seconds: float = 0.0


class FaultController:
    """Thread-safe, deterministic readiness response sequence."""

    def __init__(self, mode: str = "healthy"):
        if type(mode) is not str or mode not in ALLOWED_MODES:
            raise FaultConfigurationError("unsupported testbed fault mode")

        self.mode = mode
        self._lock = threading.Lock()
        self._requests = 0

    def next_observation(self) -> FaultObservation:
        with self._lock:
            self._requests += 1
            request_number = self._requests

        if self.mode == "outage":
            return FaultObservation(503)

        if self.mode == "latency":
            return FaultObservation(200, LATENCY_SECONDS)

        if self.mode == "timeout_response":
            return FaultObservation(504)

        if self.mode == "intermittent":
            return FaultObservation(503 if request_number % 2 else 200)

        if self.mode == "recovering":
            return FaultObservation(503 if request_number <= 3 else 200)

        if self.mode == "regression":
            if request_number <= 3 or request_number >= 7:
                return FaultObservation(503)
            return FaultObservation(200)

        return FaultObservation(200)

    def readiness_status(self) -> int:
        """Compatibility with existing status-only tests."""
        return self.next_observation().status


def controller_from_environment() -> FaultController:
    return FaultController(
        os.environ.get("NANOCLAW_TESTBED_FAULT_MODE", "healthy")
    )
