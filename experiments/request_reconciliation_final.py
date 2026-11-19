"""Strict offline reconciliation of expected and observed request IDs.

Does not attest Docker log completeness, source IPs, or request origin.
"""

from __future__ import annotations

import hashlib
import json
import re

from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_REQUESTS = 2000
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _validate_ids(values, label):
    if type(values) is not list:
        raise TrafficEvidenceError(f"{label} must be a list")
    if not 1 <= len(values) <= MAX_REQUESTS:
        raise TrafficEvidenceError(f"{label} count out of bounds")

    seen = set()
    for value in values:
        if type(value) is not str or not REQUEST_ID.fullmatch(value):
            raise TrafficEvidenceError(f"invalid {label} request ID")
        if value in seen:
            raise TrafficEvidenceError(f"duplicate {label} request ID")
        seen.add(value)

    return seen


def reconcile_request_ids(expected, observed):
    """Fail closed unless expected and observed IDs match exactly."""
    expected_set = _validate_ids(expected, "expected")
    observed_set = _validate_ids(observed, "observed")

    missing = sorted(expected_set - observed_set)
    unexpected = sorted(observed_set - expected_set)

    if missing or unexpected:
        raise TrafficEvidenceError(
            f"request reconciliation failed: "
            f"missing={len(missing)}, unexpected={len(unexpected)}"
        )

    canonical = json.dumps(
        sorted(expected_set),
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")

    return {
        "expected_request_count": len(expected_set),
        "observed_request_count": len(observed_set),
        "request_ids_match": True,
        "request_manifest_sha256": hashlib.sha256(canonical).hexdigest(),
        "source_ip_verified": False,
        "capture_completeness_verified": False,
        "runtime_origin_verified": False,
    }
