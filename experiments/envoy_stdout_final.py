"""Bounded offline extraction of Envoy JSON access logs from mixed stdout.

This is not a Docker log fetcher. Caller supplies captured bytes and an
explicit completeness assertion. Neither provenance nor completeness can
be independently established from stdout text alone.
"""

from __future__ import annotations

import hashlib
import json

from experiments.envoy_traffic_p15 import (
    FIELDS,
    MAX_EVENTS,
    MAX_LOG_BYTES,
    summarize_envoy_jsonl,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_CAPTURE_BYTES = 1_000_000
MAX_LINE_BYTES = 4096


def _reject_duplicate(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TrafficEvidenceError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise TrafficEvidenceError("nonfinite JSON value")


def extract_envoy_stdout(raw, *, capture_complete=False):
    """Extract bounded Envoy JSONL without silently dropping JSON records."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CAPTURE_BYTES:
        raise TrafficEvidenceError("invalid stdout capture size")

    if capture_complete is not True:
        raise TrafficEvidenceError("stdout capture completeness unverified")

    if not raw.endswith(b"\n"):
        raise TrafficEvidenceError("unterminated stdout capture")

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrafficEvidenceError("invalid stdout UTF-8") from exc

    selected = []
    selected_bytes = 0
    ignored_messages = 0

    for line in content.splitlines():
        if not line:
            raise TrafficEvidenceError("empty stdout line")

        encoded = line.encode("utf-8")
        if len(encoded) > MAX_LINE_BYTES:
            raise TrafficEvidenceError("oversized stdout line")

        stripped = line.lstrip()

        if not stripped.startswith(("{", "[")):
            ignored_messages += 1
            continue

        try:
            row = json.loads(
                line,
                object_pairs_hook=_reject_duplicate,
                parse_constant=_reject_constant,
            )
        except (ValueError, TypeError) as exc:
            raise TrafficEvidenceError("malformed JSON stdout record") from exc

        if type(row) is not dict or set(row) != FIELDS:
            raise TrafficEvidenceError("unexpected JSON stdout schema")

        selected.append(encoded)
        selected_bytes += len(encoded) + 1

        if len(selected) > MAX_EVENTS or selected_bytes > MAX_LOG_BYTES:
            raise TrafficEvidenceError("access-log evidence exceeds bounds")

    if len(selected) < 2:
        raise TrafficEvidenceError("insufficient Envoy access records")

    evidence = b"\n".join(selected) + b"\n"
    summary = summarize_envoy_jsonl(evidence)

    return {
        "report_version": 1,
        "evidence_source": "extracted_envoy_stdout",
        "capture_sha256": hashlib.sha256(raw).hexdigest(),
        "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        "capture_bytes": len(raw),
        "validated_event_count": len(selected),
        "ignored_non_json_messages": ignored_messages,
        "capture_complete_asserted_by_caller": True,
        "runtime_origin_verified": False,
        "source_ip_separation_verified": False,
        "detector_classification_verified": False,
        "production_traffic_verified": False,
        "mitigation_executed": False,
        "summary": summary,
        "validated_evidence_jsonl": evidence,
    }
