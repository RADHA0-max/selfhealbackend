"""Extract bounded request IDs from k6 JSON metric output."""

import json

from experiments.request_reconciliation_final import _validate_ids
from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_BYTES = 2 * 1024 * 1024
MAX_LINES = 10000


def parse_k6_manifest(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise TrafficEvidenceError("invalid k6 output size")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrafficEvidenceError("invalid k6 encoding") from exc

    ids = []
    lines = text.splitlines()

    if not 1 <= len(lines) <= MAX_LINES:
        raise TrafficEvidenceError("invalid k6 line count")

    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, TypeError) as exc:
            raise TrafficEvidenceError("invalid k6 JSON") from exc

        if record.get("type") != "Point":
            continue

        if record.get("metric") != "nanoclaw_request_manifest":
            continue

        data = record.get("data")
        if type(data) is not dict:
            raise TrafficEvidenceError("invalid k6 metric data")

        tags = data.get("tags")
        if type(tags) is not dict:
            raise TrafficEvidenceError("invalid k6 metric tags")

        if tags.get("workload") != "organic_60vu":
            raise TrafficEvidenceError("unexpected workload")

        if data.get("value") != 1:
            raise TrafficEvidenceError("invalid metric value")

        ids.append(tags.get("request_id"))

    _validate_ids(ids, "k6")
    return ids
