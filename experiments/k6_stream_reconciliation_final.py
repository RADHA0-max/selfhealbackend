"""Reconcile bounded k6 output stream with validated Envoy JSONL."""

import hashlib

from experiments.k6_stream_final import extract_k6_manifest
from experiments.envoy_reconciliation_final import reconcile_envoy_jsonl


def reconcile_k6_stream_with_envoy(k6_path, envoy_raw):
    capture = extract_k6_manifest(k6_path)
    result = reconcile_envoy_jsonl(
        envoy_raw, capture["request_ids"]
    )
    return {
        "k6_request_count": capture["request_count"],
        "k6_manifest_sha256": hashlib.sha256(
            capture["manifest_raw"]
        ).hexdigest(),
        "request_reconciliation": result,
        "k6_capture_complete_verified": False,
        "envoy_capture_complete_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }
