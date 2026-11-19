"""Reconcile validated Envoy JSONL against a caller-supplied request manifest.

Matching IDs do not independently establish request origin or log completeness.
"""

from __future__ import annotations

import json

from experiments.envoy_traffic_p15 import parse_envoy_jsonl
from experiments.request_reconciliation_final import reconcile_request_ids
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def reconcile_envoy_jsonl(raw, expected_request_ids):
    """Validate all records, then reconcile their request IDs exactly."""
    if type(raw) is not bytes:
        raise TrafficEvidenceError("Envoy evidence must be bytes")

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TrafficEvidenceError("invalid Envoy evidence encoding") from exc

    # Reuse the established strict Envoy validator before extracting IDs.
    parse_envoy_jsonl(raw)

    observed = []
    try:
        for line in text.splitlines():
            if not line:
                raise TrafficEvidenceError("blank Envoy record")
            record = json.loads(line)
            if type(record) is not dict:
                raise TrafficEvidenceError("invalid Envoy record")
            observed.append(record["request_id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise TrafficEvidenceError("invalid Envoy request ID evidence") from exc

    return reconcile_request_ids(expected_request_ids, observed)
