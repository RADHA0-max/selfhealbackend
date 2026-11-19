"""Bounded, strict, streaming Envoy evidence validation."""

import hashlib
import os
import stat

from experiments.envoy_traffic_p15 import (
    MAX_WINDOW_MS,
    parse_envoy_jsonl,
)
from experiments.request_reconciliation_final import (
    _validate_ids,
    reconcile_request_ids,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 4096
MAX_EVENTS = 2000
BATCH_EVENTS = 100


def extract_envoy_ids(path):
    """Validate complete Envoy JSONL using bounded batches."""
    if type(path) is not str or not path or "\x00" in path:
        raise TrafficEvidenceError("invalid Envoy stream path")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise TrafficEvidenceError("cannot open Envoy stream") from exc

    try:
        before = os.fstat(fd)

        if not stat.S_ISREG(before.st_mode):
            raise TrafficEvidenceError("Envoy stream must be regular file")

        if not 0 < before.st_size <= MAX_INPUT_BYTES:
            raise TrafficEvidenceError("invalid Envoy stream size")

        digest = hashlib.sha256()
        ids = []
        consumed = 0
        batch = []
        previous = None
        first = None
        last = None

        def validate_batch(lines):
            nonlocal previous, first, last

            from experiments.envoy_traffic_p15 import (
                FIELDS, METHODS, PATHS, REQUEST_ID,
                MAX_DURATION_MS, _reject_duplicate,
                _reject_constant, _text, _timestamp,
            )
            import ipaddress
            import json
            import re

            for line in lines:
                try:
                    row = json.loads(
                        line,
                        object_pairs_hook=_reject_duplicate,
                        parse_constant=_reject_constant,
                    )
                except (ValueError, TypeError, UnicodeDecodeError) as exc:
                    raise TrafficEvidenceError(
                        "invalid Envoy JSON"
                    ) from exc

                if type(row) is not dict or set(row) != FIELDS:
                    raise TrafficEvidenceError(
                        "invalid Envoy log schema"
                    )

                timestamp = _timestamp(row["timestamp"])

                ip = _text(row["client_ip"], "client_ip", 64)
                try:
                    ipaddress.ip_address(ip)
                except ValueError as exc:
                    raise TrafficEvidenceError(
                        "invalid client IP"
                    ) from exc

                if row["method"] not in METHODS:
                    raise TrafficEvidenceError(
                        "unexpected HTTP method"
                    )

                if row["path"] not in PATHS:
                    raise TrafficEvidenceError(
                        "unexpected HTTP path"
                    )

                status = row["status"]
                duration = row["duration_ms"]

                if (
                    type(status) is str
                    and re.fullmatch(r"[1-5][0-9]{2}", status)
                ):
                    status = int(status)

                if (
                    type(duration) is str
                    and re.fullmatch(r"[0-9]{1,5}", duration)
                ):
                    duration = int(duration)

                if (
                    type(status) is not int
                    or not 100 <= status <= 599
                ):
                    raise TrafficEvidenceError(
                        "invalid HTTP status"
                    )

                if (
                    type(duration) is not int
                    or not 0 <= duration <= MAX_DURATION_MS
                ):
                    raise TrafficEvidenceError(
                        "invalid request duration"
                    )

                _text(row["user_agent"], "user_agent", 256)
                request_id = _text(
                    row["request_id"], "request_id", 128
                )

                if not REQUEST_ID.fullmatch(request_id):
                    raise TrafficEvidenceError(
                        "invalid request ID"
                    )

                if previous is not None and timestamp < previous:
                    raise TrafficEvidenceError(
                        "out-of-order Envoy timestamps"
                    )

                if first is None:
                    first = timestamp

                previous = timestamp
                last = timestamp
                ids.append(request_id)

        with os.fdopen(fd, "rb", closefd=False) as stream:
            while True:
                line = stream.readline(MAX_LINE_BYTES + 1)

                if not line:
                    break

                consumed += len(line)

                if consumed > MAX_INPUT_BYTES:
                    raise TrafficEvidenceError(
                        "Envoy stream exceeds byte limit"
                    )

                if (
                    len(line) > MAX_LINE_BYTES
                    or not line.endswith(b"\n")
                ):
                    raise TrafficEvidenceError(
                        "invalid Envoy stream line"
                    )

                digest.update(line)
                batch.append(line)

                if len(ids) + len(batch) > MAX_EVENTS:
                    raise TrafficEvidenceError(
                        "too many Envoy events"
                    )

                if len(batch) == BATCH_EVENTS:
                    validate_batch(batch)
                    batch.clear()

        if batch:
            validate_batch(batch)

        if not 2 <= len(ids) <= MAX_EVENTS:
            raise TrafficEvidenceError(
                "invalid Envoy event count"
            )

        window = last - first
        window_ms = (
            window.days * 86_400_000
            + window.seconds * 1000
            + window.microseconds // 1000
        )

        if not 1 <= window_ms <= MAX_WINDOW_MS:
            raise TrafficEvidenceError(
                "invalid Envoy observation window"
            )

        after = os.fstat(fd)

        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or consumed != before.st_size
        ):
            raise TrafficEvidenceError(
                "Envoy stream changed during read"
            )

        _validate_ids(ids, "envoy")

        return {
            "request_ids": ids,
            "request_count": len(ids),
            "sha256": digest.hexdigest(),
            "input_bytes": consumed,
            "capture_complete_verified": False,
            "runtime_origin_verified": False,
            "source_ip_verified": False,
        }

    except OSError as exc:
        raise TrafficEvidenceError(
            "Envoy stream read failed"
        ) from exc

    finally:
        os.close(fd)


def reconcile_envoy_stream(path, expected_ids):
    observed = extract_envoy_ids(path)

    result = reconcile_request_ids(
        expected_ids,
        observed["request_ids"],
    )

    result["envoy_sha256"] = observed["sha256"]
    result["envoy_input_bytes"] = observed["input_bytes"]
    result["capture_complete_verified"] = False
    result["runtime_origin_verified"] = False
    result["source_ip_verified"] = False

    return result
