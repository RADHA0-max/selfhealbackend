"""Bounded, durable evidence from explicitly selected loopback HTTP tests."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from chaos.http_probe_recorder import record_http_probes, validate_probe_url
from chaos.recovery_timeline import evaluate_timeline, validate_timeline


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
MAX_REPORT_BYTES = 65536


class MeasurementError(ValueError):
    """Invalid measurement configuration or evidence."""


def evaluate_measured_http(
    url,
    *,
    experiment_id,
    count=9,
    interval_seconds=0.1,
    timeout_seconds=2.0,
    healthy_latency_ms=1000,
    opener=None,
    clock=None,
    sleep=None,
):
    """Collect real HTTP observations; never claim agent-driven recovery."""

    validate_probe_url(url)

    if type(experiment_id) is not str or not _ID.fullmatch(experiment_id):
        raise MeasurementError("invalid experiment ID")

    events = record_http_probes(
        url,
        count=count,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        opener=opener,
        clock=clock,
        sleep=sleep,
    )

    validated = validate_timeline(events)

    result = evaluate_timeline(
        validated,
        healthy_latency_ms=healthy_latency_ms,
    )

    return {
        "report_version": 1,
        "experiment_id": experiment_id,
        "evidence_source": "measured_loopback_http",
        "endpoint": url,
        "events": validated,
        "healthy_latency_ms": healthy_latency_ms,
        "timeline": result,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "envoy_verified": False,
        "production_recovery_verified": False,
    }


def write_measured_report(directory, report):
    """Persist an immutable, bounded JSON report without replacing files."""

    if not isinstance(report, dict):
        raise MeasurementError("report must be an object")

    experiment_id = report.get("experiment_id")

    if type(experiment_id) is not str or not _ID.fullmatch(experiment_id):
        raise MeasurementError("invalid experiment ID")

    if report.get("evidence_source") != "measured_loopback_http":
        raise MeasurementError("unsupported evidence source")

    if any(report.get(key) is not False for key in (
        "mitigation_executed",
        "recovery_attributed_to_agent",
        "envoy_verified",
        "production_recovery_verified",
    )):
        raise MeasurementError("unsupported recovery claim")

    expected_keys = {
        "report_version",
        "experiment_id",
        "evidence_source",
        "endpoint",
        "events",
        "healthy_latency_ms",
        "timeline",
        "mitigation_executed",
        "recovery_attributed_to_agent",
        "envoy_verified",
        "production_recovery_verified",
    }

    if set(report) != expected_keys or report["report_version"] != 1:
        raise MeasurementError("invalid report schema")

    validate_probe_url(report["endpoint"])

    try:
        events = validate_timeline(report["events"])
        expected_timeline = evaluate_timeline(
            events,
            healthy_latency_ms=report["healthy_latency_ms"],
        )
    except (ValueError, TypeError) as exc:
        raise MeasurementError("invalid measured observations") from exc

    if report["timeline"] != expected_timeline:
        raise MeasurementError("timeline does not match observations")

    encoded = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    if len(encoded) > MAX_REPORT_BYTES:
        raise MeasurementError("report exceeds size limit")

    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)

    final_path = destination / f"{experiment_id}.json"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".measurement-",
        suffix=".tmp",
        dir=destination,
    )

    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

        os.link(temporary_name, final_path)

        directory_fd = os.open(destination, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        os.unlink(temporary_name)

    return final_path
