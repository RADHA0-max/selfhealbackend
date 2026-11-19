"""Fail-closed reconciliation of k6 metric IDs and Envoy access records.

This proves equality of IDs in two supplied byte streams, not source
authenticity, traffic isolation, or completeness of either capture.
"""

from experiments.k6_manifest_final import parse_k6_manifest
from experiments.envoy_reconciliation_final import reconcile_envoy_jsonl
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def reconcile_k6_envoy(k6_raw, envoy_raw):
    """Validate both streams and require an exact request-ID match."""
    if type(k6_raw) is not bytes or type(envoy_raw) is not bytes:
        raise TrafficEvidenceError("both evidence streams must be bytes")

    expected_ids = parse_k6_manifest(k6_raw)

    # Existing strict Envoy parser and request reconciliation reject
    # malformed records, missing IDs, unexpected IDs, and duplicates.
    result = reconcile_envoy_jsonl(envoy_raw, expected_ids)

    return {
        "k6_manifest_request_count": len(expected_ids),
        "request_reconciliation": result,
        "k6_capture_complete_verified": False,
        "envoy_capture_complete_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }
