"""Read-only reconciliation of streaming k6 and Envoy evidence."""

import hashlib

from experiments.envoy_stream_final import reconcile_envoy_stream
from experiments.k6_stream_final import extract_k6_manifest


def reconcile_k6_envoy_stream(k6_path, envoy_path):
    k6 = extract_k6_manifest(k6_path)

    reconciliation = reconcile_envoy_stream(
        envoy_path,
        k6["request_ids"],
    )

    return {
        "k6_request_count": k6["request_count"],
        "k6_manifest_sha256": hashlib.sha256(
            k6["manifest_raw"]
        ).hexdigest(),
        "request_reconciliation": reconciliation,
        "k6_capture_complete_verified": False,
        "envoy_capture_complete_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }
