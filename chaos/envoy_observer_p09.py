"""Bounded HTTP observer for the isolated Person C Envoy testbed."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from chaos.recovery_timeline import evaluate_timeline


ENVOY_URL = "http://testbed-envoy:10000/ready"
MAX_OBSERVATIONS = 10
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


class ObserverError(ValueError):
    """Invalid observer configuration or incomplete measurements."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        raise ObserverError("redirects are prohibited")


def observe_envoy(
    *,
    experiment_id: str,
    count: int = 9,
    interval_seconds: float = 0.1,
    timeout_seconds: float = 2.0,
    healthy_latency_ms: int = 1000,
):
    """Measure Envoy inside the isolated testbed network."""

    if type(experiment_id) is not str or not _ID.fullmatch(experiment_id):
        raise ObserverError("invalid experiment ID")

    if type(count) is not int or not 2 <= count <= MAX_OBSERVATIONS:
        raise ObserverError("count must be 2..10")

    if type(interval_seconds) not in (int, float) or not (
        0.1 <= interval_seconds <= 10
    ):
        raise ObserverError("invalid interval")

    if type(timeout_seconds) not in (int, float) or not (
        0.1 <= timeout_seconds <= 5
    ):
        raise ObserverError("invalid timeout")

    if type(healthy_latency_ms) is not int or not (
        1 <= healthy_latency_ms <= 60000
    ):
        raise ObserverError("invalid latency threshold")

    opener = build_opener(ProxyHandler({}), NoRedirect())
    events = []
    origin = time.monotonic()

    for index in range(count):
        if index:
            time.sleep(interval_seconds)

        started = time.monotonic()

        try:
            request = Request(ENVOY_URL, method="GET")

            with opener.open(request, timeout=timeout_seconds) as response:
                status = response.status

        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise ObserverError("redirect prohibited") from exc
            status = exc.code

        except (URLError, TimeoutError, OSError) as exc:
            raise ObserverError("incomplete Envoy observation") from exc

        finished = time.monotonic()

        timestamp_ms = int((started - origin) * 1000)

        if events and timestamp_ms <= events[-1]["time_ms"]:
            raise ObserverError("insufficient timestamp resolution")

        events.append({
            "time_ms": timestamp_ms,
            "target": "api",
            "status": status,
            "latency_ms": int((finished - started) * 1000),
        })

    timeline = evaluate_timeline(
        events,
        healthy_latency_ms=healthy_latency_ms,
    )

    return {
        "report_version": 1,
        "experiment_id": experiment_id,
        "evidence_source": "isolated_envoy_http",
        "endpoint": ENVOY_URL,
        "events": events,
        "healthy_latency_ms": healthy_latency_ms,
        "timeline": timeline,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }


def write_observation(directory: str | Path, report: dict):
    """Write a bounded, immutable observation record."""

    if not isinstance(report, dict):
        raise ObserverError("invalid report")

    experiment_id = report.get("experiment_id")

    if type(experiment_id) is not str or not _ID.fullmatch(experiment_id):
        raise ObserverError("invalid experiment ID")

    if report.get("evidence_source") != "isolated_envoy_http":
        raise ObserverError("invalid evidence source")

    if report.get("endpoint") != ENVOY_URL:
        raise ObserverError("unexpected observation endpoint")

    for key in (
        "mitigation_executed",
        "recovery_attributed_to_agent",
        "production_recovery_verified",
    ):
        if report.get(key) is not False:
            raise ObserverError("unsupported recovery claim")

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
        "production_recovery_verified",
    }

    if set(report) != expected_keys or report["report_version"] != 1:
        raise ObserverError("invalid report schema")

    try:
        expected_timeline = evaluate_timeline(
            report["events"],
            healthy_latency_ms=report["healthy_latency_ms"],
        )
    except (ValueError, TypeError) as exc:
        raise ObserverError("invalid observation timeline") from exc

    if report["timeline"] != expected_timeline:
        raise ObserverError("timeline does not match observations")

    encoded = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    if len(encoded) > 65536:
        raise ObserverError("observation exceeds size limit")

    destination = Path(directory)

    if not destination.is_dir():
        raise ObserverError("output directory must already exist")

    final_path = destination / f"{experiment_id}.json"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".envoy-observation-",
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


def main():
    experiment_id = os.environ.get("NANOCLAW_OBSERVATION_ID", "")

    report = observe_envoy(experiment_id=experiment_id)

    path = write_observation(
        "/observations",
        report,
    )

    print(json.dumps({
        "experiment_id": experiment_id,
        "observation_count": len(report["events"]),
        "outcome": report["timeline"]["observation_outcome"],
        "report_path": str(path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
