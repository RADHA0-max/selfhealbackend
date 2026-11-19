"""Bounded, deterministic analysis of synthetic testbed traffic traces.

This module does not classify production traffic or authenticate source IPs.
"""

from __future__ import annotations

import ipaddress
import json
import math
import re
from collections import Counter
from typing import Any


class TrafficEvidenceError(ValueError):
    pass


MAX_EVENTS = 2000
MAX_DURATION_MS = 600_000
MAX_BYTES = 512_000

SCENARIOS = frozenset({
    "organic",
    "synthetic_ddos",
    "synthetic_scraper",
    "nat_negative_control",
    "synthetic_ambiguous",
    "cache_probe",
})

PATHS = frozenset({
    "/health",
    "/ready",
    "/api/data",
})

SESSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _integer(value: Any, low: int, high: int, field: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise TrafficEvidenceError(f"invalid {field}")
    return value


def _session(value: Any) -> str:
    if not isinstance(value, str) or not SESSION_RE.fullmatch(value):
        raise TrafficEvidenceError("invalid session")
    return value


def validate_events(events: Any) -> list[dict]:
    if not isinstance(events, list) or not 2 <= len(events) <= MAX_EVENTS:
        raise TrafficEvidenceError("invalid event count")

    try:
        encoded = json.dumps(
            events, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise TrafficEvidenceError("invalid JSON events") from exc

    if len(encoded) > MAX_BYTES:
        raise TrafficEvidenceError("traffic evidence too large")

    validated = []
    previous_time = -1

    for event in events:
        if type(event) is not dict or set(event) != {
            "time_ms", "scenario", "path", "status",
            "session", "client_ip",
        }:
            raise TrafficEvidenceError("invalid event schema")

        time_ms = _integer(
            event["time_ms"], 0, MAX_DURATION_MS, "time_ms"
        )

        if time_ms < previous_time:
            raise TrafficEvidenceError("events out of order")

        previous_time = time_ms

        scenario = event["scenario"]
        path = event["path"]

        if type(scenario) is not str or scenario not in SCENARIOS:
            raise TrafficEvidenceError("invalid scenario")

        if type(path) is not str or path not in PATHS:
            raise TrafficEvidenceError("invalid path")

        status = _integer(event["status"], 100, 599, "status")
        session = _session(event["session"])

        address = event["client_ip"]
        if type(address) is not str:
            raise TrafficEvidenceError("invalid client IP")

        try:
            parsed_ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise TrafficEvidenceError("invalid client IP") from exc

        # Only reserved documentation addresses are accepted in synthetic
        # fixtures. This field is a label, never proof of network identity.
        if not (
            isinstance(parsed_ip, ipaddress.IPv4Address)
            and parsed_ip in ipaddress.ip_network("192.0.2.0/24")
        ):
            raise TrafficEvidenceError("non-documentation synthetic IP")

        validated.append({
            "time_ms": time_ms,
            "scenario": scenario,
            "path": path,
            "status": status,
            "session": session,
            "client_ip": address,
        })

    if validated[-1]["time_ms"] == validated[0]["time_ms"]:
        raise TrafficEvidenceError("zero observation duration")

    return validated


def summarize_traffic(events: Any) -> dict:
    rows = validate_events(events)

    duration_ms = rows[-1]["time_ms"] - rows[0]["time_ms"]
    request_count = len(rows)

    scenarios = Counter(row["scenario"] for row in rows)
    paths = Counter(row["path"] for row in rows)
    sessions = {row["session"] for row in rows}
    ips = {row["client_ip"] for row in rows}

    gaps = [
        rows[i]["time_ms"] - rows[i - 1]["time_ms"]
        for i in range(1, request_count)
    ]

    return {
        "summary_version": 1,
        "evidence_source": "synthetic_fixture",
        "request_count": request_count,
        "duration_ms": duration_ms,
        "requests_per_second": round(
            request_count * 1000 / duration_ms, 3
        ),
        "unique_sessions": len(sessions),
        "synthetic_ip_labels": len(ips),
        "http_5xx_count": sum(
            row["status"] >= 500 for row in rows
        ),
        "min_gap_ms": min(gaps),
        "max_gap_ms": max(gaps),
        "scenario_counts": dict(sorted(scenarios.items())),
        "path_counts": dict(sorted(paths.items())),
        "source_ip_separation_verified": False,
        "detector_classification_verified": False,
        "production_traffic_verified": False,
    }


def compare_traffic(organic: Any, candidate: Any) -> dict:
    baseline = summarize_traffic(organic)
    observed = summarize_traffic(candidate)

    if baseline["scenario_counts"] != {
        "organic": baseline["request_count"]
    }:
        raise TrafficEvidenceError("baseline must be organic")

    return {
        "comparison_version": 1,
        "baseline": baseline,
        "candidate": observed,
        "rate_ratio": round(
            observed["requests_per_second"]
            / baseline["requests_per_second"],
            3,
        ),
        "session_count_difference": (
            observed["unique_sessions"]
            - baseline["unique_sessions"]
        ),
        "detector_classification_verified": False,
        "production_traffic_verified": False,
    }
