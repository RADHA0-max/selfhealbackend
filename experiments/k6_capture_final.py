"""Read a bounded k6 JSON output file and reconcile it with Envoy evidence.

Only a validated local regular file is accepted. Matching IDs do not prove
capture completeness, runtime provenance, or source-IP authenticity.
"""

import hashlib
import os
import stat

from experiments.k6_manifest_final import MAX_BYTES, parse_k6_manifest
from experiments.k6_envoy_reconciliation_final import reconcile_k6_envoy
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def read_k6_capture(path):
    if type(path) is not str or not path or "\x00" in path:
        raise TrafficEvidenceError("invalid k6 capture path")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    try:
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise TrafficEvidenceError("k6 capture must be regular file")
            if not 0 < before.st_size <= MAX_BYTES:
                raise TrafficEvidenceError("invalid k6 capture size")

            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)

            after = os.fstat(fd)
            if (
                before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise TrafficEvidenceError("k6 capture changed during read")
        finally:
            os.close(fd)
    except (OSError, ValueError) as exc:
        raise TrafficEvidenceError("cannot read k6 capture") from exc

    if not 0 < len(raw) <= MAX_BYTES:
        raise TrafficEvidenceError("invalid k6 capture length")

    if len(raw) != before.st_size:
        raise TrafficEvidenceError("incomplete k6 capture read")

    ids = parse_k6_manifest(raw)

    return {
        "raw": raw,
        "request_ids": ids,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "capture_complete_verified": False,
        "runtime_origin_verified": False,
    }


def reconcile_k6_file_with_envoy(k6_path, envoy_raw):
    capture = read_k6_capture(k6_path)
    report = reconcile_k6_envoy(capture["raw"], envoy_raw)
    report["k6_capture_sha256"] = capture["sha256"]
    return report
