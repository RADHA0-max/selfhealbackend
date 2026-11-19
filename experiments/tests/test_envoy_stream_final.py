"""Offline tests for strict streaming Envoy evidence."""

import json
import tempfile
import unittest
from pathlib import Path

from experiments.envoy_stream_final import (
    extract_envoy_ids,
    reconcile_envoy_stream,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def event(index, **changes):
    row = {
        "timestamp": (
            f"2026-11-18T12:00:{index % 60:02d}Z"
        ),
        "client_ip": "172.20.0.10",
        "method": "GET",
        "path": "/ready",
        "status": 200,
        "duration_ms": 5,
        "user_agent": "NanoClaw-Test",
        "request_id": f"offline-organic-vu-1-iter-{index}",
    }
    row.update(changes)
    return row


class EnvoyStreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "envoy.jsonl"

    def write(self, rows):
        self.path.write_bytes(
            b"".join(
                json.dumps(row).encode() + b"\n"
                for row in rows
            )
        )

    def test_valid_two_events(self):
        self.write([event(0), event(1)])
        result = extract_envoy_ids(str(self.path))
        self.assertEqual(result["request_count"], 2)
        self.assertFalse(result["runtime_origin_verified"])

    def test_reconciliation(self):
        self.write([event(0), event(1)])
        ids = [
            "offline-organic-vu-1-iter-0",
            "offline-organic-vu-1-iter-1",
        ]
        result = reconcile_envoy_stream(
            str(self.path), ids
        )
        self.assertTrue(result["request_ids_match"])

    def test_duplicate_id_rejected(self):
        self.write([
            event(0),
            event(
                1,
                request_id="offline-organic-vu-1-iter-0",
            ),
        ])
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_ids(str(self.path))

    def test_invalid_ip_rejected(self):
        self.write([
            event(0),
            event(1, client_ip="not-an-ip"),
        ])
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_ids(str(self.path))

    def test_duplicate_json_key_rejected(self):
        raw = (
            b'{"timestamp":"2026-11-18T12:00:00Z",'
            b'"timestamp":"2026-11-18T12:00:01Z"}\n'
        )
        self.path.write_bytes(raw + raw)
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_ids(str(self.path))

    def test_missing_id_rejected(self):
        self.write([event(0), event(1)])
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_stream(
                str(self.path),
                ["offline-organic-vu-1-iter-0"],
            )


if __name__ == "__main__":
    unittest.main()
