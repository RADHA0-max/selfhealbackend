"""Bounded, offline validation of isolated Envoy access-log evidence."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from experiments.envoy_traffic_p15 import (
    MAX_LOG_BYTES,
    parse_envoy_jsonl,
    summarize_envoy_jsonl,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def analyze_envoy_evidence(filename):
    """Analyze one bounded, validated Envoy JSONL evidence file.

    No network access, detector classification, or mitigation.
    """
    path = Path(filename)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise TrafficEvidenceError("unable to open evidence") from exc

    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(stream.fileno())

        if not stat.S_ISREG(metadata.st_mode):
            raise TrafficEvidenceError("evidence must be a regular file")

        if not 1 <= metadata.st_size <= MAX_LOG_BYTES:
            raise TrafficEvidenceError("invalid evidence size")

        raw = stream.read(MAX_LOG_BYTES + 1)

    if len(raw) > MAX_LOG_BYTES:
        raise TrafficEvidenceError("evidence exceeds limit")

    # Strict validation: reject malformed or unexpected records.
    events = parse_envoy_jsonl(raw)
    summary = summarize_envoy_jsonl(raw)

    return {
        "report_version": 1,
        "evidence_source": "validated_envoy_jsonl",
        "evidence_sha256": hashlib.sha256(raw).hexdigest(),
        "validated_event_count": len(events),
        "summary": summary,
        "source_ip_separation_verified": False,
        "detector_classification_verified": False,
        "production_traffic_verified": False,
        "mitigation_executed": False,
    }
