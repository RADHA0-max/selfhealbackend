"""Replay-safe advisory incident evaluation from isolated Envoy evidence.

This is NOT a production detector adapter or autonomous mitigation path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.durable_offline_incident import IncidentReplayError, evaluate_durable_offline_incident
from agent.signal_adapter import signal_to_evidence
from experiments.run_record import RunRecordError
from chaos.envoy_observer_p09 import ENVOY_URL
from chaos.recovery_timeline import evaluate_timeline, validate_timeline


MAX_REPORT_BYTES = 65536
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,61}\Z")

EXPECTED_KEYS = frozenset({
    "report_version",
    "experiment_id",
    "evidence_source",
    "endpoint",
    "events",
    "healthy_latency_ms",
    "timeline",
    "mitigation_executed",
    "recovery_attributed_to_agent",
    "production_recovery_verified",
})


class MeasuredIncidentError(ValueError):
    """Invalid or unsupported measured incident evidence."""


def _unique_pairs(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise MeasuredIncidentError("duplicate JSON key")
        result[key] = value

    return result


def load_measured_report(path: str | Path) -> dict[str, Any]:
    """Load bounded, locally captured Envoy evidence; fail closed."""

    source = Path(path)

    if source.is_symlink() or not source.is_file():
        raise MeasuredIncidentError("invalid evidence file")

    if source.stat().st_size > MAX_REPORT_BYTES:
        raise MeasuredIncidentError("evidence exceeds size limit")

    try:
        with source.open("rb") as stream:
            raw = stream.read(MAX_REPORT_BYTES + 1)

        if len(raw) > MAX_REPORT_BYTES:
            raise MeasuredIncidentError("evidence exceeds size limit")

        report = json.loads(
            raw,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                MeasuredIncidentError("nonfinite JSON value")
            ),
        )

    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise MeasuredIncidentError("invalid evidence JSON") from exc

    if type(report) is not dict or set(report) != EXPECTED_KEYS:
        raise MeasuredIncidentError("unsupported evidence schema")

    if type(report["report_version"]) is not int or report["report_version"] != 1:
        raise MeasuredIncidentError("invalid report version")

    experiment_id = report["experiment_id"]

    # Reserve two characters for the "-N" observation suffix.
    if type(experiment_id) is not str or not _ID.fullmatch(experiment_id):
        raise MeasuredIncidentError("invalid experiment ID")

    if source.name != f"{experiment_id}.json":
        raise MeasuredIncidentError("filename does not match experiment ID")

    if report["evidence_source"] != "isolated_envoy_http":
        raise MeasuredIncidentError("unsupported evidence source")

    if report["endpoint"] != ENVOY_URL:
        raise MeasuredIncidentError("unexpected endpoint")

    for key in (
        "mitigation_executed",
        "recovery_attributed_to_agent",
        "production_recovery_verified",
    ):
        if report[key] is not False:
            raise MeasuredIncidentError("unsupported recovery claim")

    threshold = report["healthy_latency_ms"]

    if type(threshold) is not int or not 1 <= threshold <= 60000:
        raise MeasuredIncidentError("invalid latency threshold")

    try:
        events = validate_timeline(report["events"])
        expected_timeline = evaluate_timeline(
            events,
            healthy_latency_ms=threshold,
        )
    except (ValueError, TypeError) as exc:
        raise MeasuredIncidentError("invalid observation timeline") from exc

    if len(events) > 10:
        raise MeasuredIncidentError("too many observations")

    # Compare canonical JSON as well as values: Python considers True == 1.
    supplied = json.dumps(
        report["timeline"], sort_keys=True, allow_nan=False
    )
    expected = json.dumps(
        expected_timeline, sort_keys=True, allow_nan=False
    )

    if supplied != expected:
        raise MeasuredIncidentError("timeline does not match measurements")

    return report


def _signals_from_report(report: dict[str, Any]):
    """Convert validated observations into provisional, synthetic-format probes."""

    experiment_id = report["experiment_id"]
    events = report["events"]

    signals = []

    for index, event in enumerate(events):
        signal = {
            "signal_id": f"{experiment_id}-{index}",
            "target": event["target"],
            "status": event["status"],
            "latency_ms": event["latency_ms"],
        }

        signal_to_evidence(signal)
        signals.append(signal)

    return signals[0], signals[1:]


def evaluate_measured_incident(
    rpc: Any,
    report_path: str | Path,
    output_dir: str | Path,
    *,
    required_healthy: int = 3,
) -> dict[str, Any]:
    """Evaluate a recorded Envoy incident, with durable replay protection."""

    report = load_measured_report(report_path)

    if not 2 <= len(report["events"]) <= 10:
        raise MeasuredIncidentError("unsupported observation count")

    if report["events"][0]["status"] < 400:
        raise MeasuredIncidentError(
            "baseline is not an HTTP failure; no incident diagnosis"
        )

    before, observations = _signals_from_report(report)

    try:
        record = evaluate_durable_offline_incident(
            rpc,
            before,
            observations,
            output_dir,
            required_healthy=required_healthy,
        )
    except RunRecordError as exc:
        raise IncidentReplayError(
            "incident already reserved or recorded"
        ) from exc

    # The P07 verifier intentionally requires every post-baseline
    # observation to be healthy. The P09 timeline instead allows failures
    # before a sustained healthy streak. Preserve both interpretations.
    timeline_outcome = report["timeline"]["observation_outcome"]
    conservative_outcome = record["result"]["observation_outcome"]

    return {
        "integration_version": 1,
        "observed_sustained_recovery": timeline_outcome,
        "uninterrupted_recovery": conservative_outcome,
        "experiment_id": report["experiment_id"],
        "evidence_source": "isolated_envoy_http",
        "incident_record": record,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }
