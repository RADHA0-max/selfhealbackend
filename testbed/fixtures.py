"""Deterministic synthetic incidents. No infrastructure access."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IncidentFixture:
    case_id: str
    evidence: dict
    expected_category: str
    expected_target: str
    expected_action: str


def build_fixtures() -> tuple[IncidentFixture, ...]:
    """Return offline cases; labels never enter model evidence."""
    return (
        IncidentFixture(
            "DB-503",
            {"probes": {"database": {"status": 503}}},
            "dependency_failure",
            "database",
            "investigate_database",
        ),
        IncidentFixture(
            "API-503",
            {"probes": {"api": {"status": 503}}},
            "service_failure",
            "api",
            "investigate_api",
        ),
        IncidentFixture(
            "AUTH-503",
            {"probes": {"auth": {"status": 503}}},
            "service_failure",
            "auth",
            "investigate_auth",
        ),
        IncidentFixture(
            "WORKER-503",
            {"probes": {"worker": {"status": 503}}},
            "service_failure",
            "worker",
            "investigate_worker",
        ),
        IncidentFixture(
            "API-LATENCY",
            {"probes": {"api": {"status": 200, "latency_ms": 2600}}},
            "latency",
            "api",
            "investigate_latency",
        ),
        IncidentFixture(
            "UNKNOWN",
            {"probes": {}},
            "unknown",
            "unknown",
            "collect_more_evidence",
        ),
    )
