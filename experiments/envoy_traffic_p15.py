"""Read-only, bounded analysis of captured Envoy access-log JSONL.

Access-log fields are observations, not authenticated client identities.
No detector classification, mitigation, or production claims are made.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import os
import re
import stat
from collections import Counter
from pathlib import Path

from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_LOG_BYTES = 512_000
MAX_EVENTS = 2000
MAX_WINDOW_MS = 600_000
MAX_DURATION_MS = 60_000

FIELDS = frozenset({
    "timestamp",
    "client_ip",
    "method",
    "path",
    "status",
    "duration_ms",
    "user_agent",
    "request_id",
})

PATHS = frozenset({"/health", "/ready", "/api/data"})
METHODS = frozenset({"GET"})
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{0,128}\Z")


def _reject_duplicate(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TrafficEvidenceError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise TrafficEvidenceError("nonfinite JSON value")


def _text(value, field, maximum=256):
    if type(value) is not str or len(value) > maximum:
        raise TrafficEvidenceError(f"invalid {field}")
    if CONTROL.search(value):
        raise TrafficEvidenceError(f"control characters in {field}")
    return value


def _timestamp(value):
    value = _text(value, "timestamp", 64)

    try:
        parsed = dt.datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise TrafficEvidenceError("invalid timestamp") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrafficEvidenceError("timestamp must have timezone")

    return parsed


def parse_envoy_jsonl(raw: bytes) -> list[dict]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_LOG_BYTES:
        raise TrafficEvidenceError("invalid log size")

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrafficEvidenceError("invalid UTF-8") from exc

    lines = content.splitlines()

    if not 2 <= len(lines) <= MAX_EVENTS:
        raise TrafficEvidenceError("invalid event count")

    events = []
    previous = None

    for line in lines:
        if not line or len(line.encode("utf-8")) > 4096:
            raise TrafficEvidenceError("invalid log line")

        try:
            row = json.loads(
                line,
                object_pairs_hook=_reject_duplicate,
                parse_constant=_reject_constant,
            )
        except (ValueError, TypeError) as exc:
            raise TrafficEvidenceError("invalid Envoy JSON") from exc

        if type(row) is not dict or set(row) != FIELDS:
            raise TrafficEvidenceError("invalid Envoy log schema")

        timestamp = _timestamp(row["timestamp"])

        if previous is not None and timestamp < previous:
            raise TrafficEvidenceError("out-of-order timestamps")

        previous = timestamp

        ip = _text(row["client_ip"], "client_ip", 64)

        try:
            ipaddress.ip_address(ip)
        except ValueError as exc:
            raise TrafficEvidenceError("invalid client IP") from exc

        if row["method"] not in METHODS:
            raise TrafficEvidenceError("unexpected HTTP method")

        if row["path"] not in PATHS:
            raise TrafficEvidenceError("unexpected HTTP path")

        status = row["status"]
        duration = row["duration_ms"]

        # Envoy json_format often serializes substitutions as strings.
        if type(status) is str and re.fullmatch(r"[1-5][0-9]{2}", status):
            status = int(status)

        if type(duration) is str and re.fullmatch(r"[0-9]{1,5}", duration):
            duration = int(duration)

        if type(status) is not int or not 100 <= status <= 599:
            raise TrafficEvidenceError("invalid HTTP status")

        if type(duration) is not int or not 0 <= duration <= MAX_DURATION_MS:
            raise TrafficEvidenceError("invalid request duration")

        agent = _text(row["user_agent"], "user_agent", 256)
        request_id = _text(row["request_id"], "request_id", 128)

        if not REQUEST_ID.fullmatch(request_id):
            raise TrafficEvidenceError("invalid request ID")

        events.append({
            "timestamp": timestamp,
            "client_ip": ip,
            "method": row["method"],
            "path": row["path"],
            "status": status,
            "duration_ms": duration,
            "user_agent": agent,
            "request_id": request_id,
        })

    delta = events[-1]["timestamp"] - events[0]["timestamp"]
    window_ms = (
        delta.days * 86_400_000
        + delta.seconds * 1000
        + delta.microseconds // 1000
    )

    if not 1 <= window_ms <= MAX_WINDOW_MS:
        raise TrafficEvidenceError("invalid observation window")

    return events


def summarize_envoy_jsonl(raw: bytes) -> dict:
    events = parse_envoy_jsonl(raw)

    delta = events[-1]["timestamp"] - events[0]["timestamp"]
    window_ms = (
        delta.days * 86_400_000
        + delta.seconds * 1000
        + delta.microseconds // 1000
    )

    gaps = [
        int(
            (events[i]["timestamp"] - events[i - 1]["timestamp"])
            .total_seconds() * 1000
        )
        for i in range(1, len(events))
    ]

    paths = Counter(event["path"] for event in events)

    return {
        "summary_version": 1,
        "evidence_source": "captured_envoy_access_log",
        "request_count": len(events),
        "window_ms": window_ms,
        "requests_per_second": round(
            len(events) * 1000 / window_ms, 3
        ),
        "unique_observed_ip_values": len({
            event["client_ip"] for event in events
        }),
        "unique_user_agent_values": len({
            event["user_agent"] for event in events
        }),
        "http_5xx_count": sum(
            event["status"] >= 500 for event in events
        ),
        "min_gap_ms": min(gaps),
        "max_gap_ms": max(gaps),
        "path_counts": dict(sorted(paths.items())),
        "source_ip_separation_verified": False,
        "detector_classification_verified": False,
        "production_traffic_verified": False,
        "mitigation_executed": False,
    }


def summarize_envoy_file(filename) -> dict:
    """Read a bounded regular file without following a final symlink."""
    path = Path(filename)

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise TrafficEvidenceError("unable to open log file") from exc

    try:
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())

            if not stat.S_ISREG(metadata.st_mode):
                raise TrafficEvidenceError("not a regular log file")

            if not 1 <= metadata.st_size <= MAX_LOG_BYTES:
                raise TrafficEvidenceError("invalid log file size")

            raw = stream.read(MAX_LOG_BYTES + 1)

    except OSError as exc:
        raise TrafficEvidenceError("unable to read log file") from exc

    return summarize_envoy_jsonl(raw)
