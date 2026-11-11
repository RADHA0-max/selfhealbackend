"""Classify offline diagnosis failures without changing runner statuses."""

from agent.diagnosis import DiagnosisError
from agent.rpc_client import RPCError


def classify_failure(exc: Exception) -> str:
    """Return a bounded, non-sensitive failure category."""
    if isinstance(exc, RPCError):
        return "transport_error"

    if isinstance(exc, TimeoutError):
        return "transport_error"

    if isinstance(exc, DiagnosisError):
        message = str(exc)

        if message == "invalid diagnosis JSON":
            return "invalid_json"

        return "invalid_schema"

    return "agent_error"
