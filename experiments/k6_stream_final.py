"""Bounded streaming extraction of k6 request-manifest metrics.

The input is a completed, trusted local k6 JSON-output file.
The extracted manifest remains unverified until reconciled with Envoy.
"""

import json
import os
import stat

from experiments.k6_manifest_final import parse_k6_manifest
from experiments.envoy_traffic_p15 import (
    _reject_duplicate,
    _reject_constant,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_REQUESTS = 2000


def extract_k6_manifest(path):
    if type(path) is not str or not path or "\x00" in path:
        raise TrafficEvidenceError("invalid k6 stream path")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise TrafficEvidenceError("cannot open k6 stream") from exc

    try:
        before = os.fstat(fd)

        if not stat.S_ISREG(before.st_mode):
            raise TrafficEvidenceError("k6 stream must be regular file")

        if not 0 < before.st_size <= MAX_INPUT_BYTES:
            raise TrafficEvidenceError("invalid k6 stream size")

        manifest = []
        manifest_size = 0
        consumed = 0

        with os.fdopen(fd, "rb", closefd=False) as stream:
            while True:
                line = stream.readline(MAX_LINE_BYTES + 1)
                if not line:
                    break

                consumed += len(line)

                if consumed > MAX_INPUT_BYTES:
                    raise TrafficEvidenceError("k6 stream exceeds limit")

                if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                    raise TrafficEvidenceError("invalid k6 stream line")

                try:
                    record = json.loads(
                        line,
                        object_pairs_hook=_reject_duplicate,
                        parse_constant=_reject_constant,
                    )
                except (ValueError, UnicodeDecodeError) as exc:
                    raise TrafficEvidenceError("invalid k6 stream JSON") from exc

                if type(record) is not dict:
                    raise TrafficEvidenceError("invalid k6 stream record")

                if (
                    record.get("type") == "Point"
                    and record.get("metric") == "nanoclaw_request_manifest"
                ):
                    manifest_size += len(line)

                    if manifest_size > MAX_MANIFEST_BYTES:
                        raise TrafficEvidenceError("manifest too large")

                    manifest.append(line)

                    if len(manifest) > MAX_REQUESTS:
                        raise TrafficEvidenceError("too many manifest requests")

        after = os.fstat(fd)

        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or consumed != before.st_size
        ):
            raise TrafficEvidenceError("k6 stream changed during read")

        raw = b"".join(manifest)
        request_ids = parse_k6_manifest(raw)

        return {
            "manifest_raw": raw,
            "request_ids": request_ids,
            "request_count": len(request_ids),
            "input_bytes": consumed,
            "capture_complete_verified": False,
            "runtime_origin_verified": False,
        }

    except OSError as exc:
        raise TrafficEvidenceError("k6 stream read failed") from exc
    finally:
        os.close(fd)
