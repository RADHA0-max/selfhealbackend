import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments.k6_capture_final import (
    read_k6_capture,
    reconcile_k6_file_with_envoy,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def k6_point(request_id):
    return {
        "type": "Point",
        "metric": "nanoclaw_request_manifest",
        "data": {
            "value": 1,
            "tags": {
                "request_id": request_id,
                "workload": "organic_60vu",
            },
        },
    }


def envoy_record(request_id, second):
    return {
        "timestamp": f"2026-11-17T00:00:{second:02d}Z",
        "client_ip": "172.28.0.10",
        "method": "GET",
        "path": "/ready",
        "status": 200,
        "duration_ms": 12,
        "user_agent": "NanoClaw-Organic-P16/1.0",
        "request_id": request_id,
    }


def encode(records):
    return (
        "\n".join(json.dumps(record) for record in records) + "\n"
    ).encode()


class TestK6CaptureFinal(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "k6.jsonl"
        self.raw = encode([k6_point("req-1"), k6_point("req-2")])
        self.path.write_bytes(self.raw)

    def test_read_capture(self):
        result = read_k6_capture(str(self.path))
        self.assertEqual(result["request_ids"], ["req-1", "req-2"])
        self.assertEqual(
            result["sha256"], hashlib.sha256(self.raw).hexdigest()
        )
        self.assertFalse(result["capture_complete_verified"])

    def test_reconcile_capture(self):
        envoy = encode([
            envoy_record("req-2", 0),
            envoy_record("req-1", 1),
        ])
        report = reconcile_k6_file_with_envoy(str(self.path), envoy)
        self.assertEqual(report["k6_manifest_request_count"], 2)
        self.assertFalse(report["runtime_origin_verified"])

    def test_missing_file(self):
        with self.assertRaises(TrafficEvidenceError):
            read_k6_capture(str(self.path) + ".missing")

    def test_empty_file(self):
        self.path.write_bytes(b"")
        with self.assertRaises(TrafficEvidenceError):
            read_k6_capture(str(self.path))

    def test_oversized_file(self):
        self.path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        with self.assertRaises(TrafficEvidenceError):
            read_k6_capture(str(self.path))

    def test_symlink_rejected(self):
        link = Path(self.tmp.name) / "link"
        link.symlink_to(self.path)
        with self.assertRaises(TrafficEvidenceError):
            read_k6_capture(str(link))

    def test_directory_rejected(self):
        with self.assertRaises(TrafficEvidenceError):
            read_k6_capture(self.tmp.name)

    def test_invalid_path(self):
        for value in (None, "", 123, "bad\x00path"):
            with self.subTest(value=value):
                with self.assertRaises(TrafficEvidenceError):
                    read_k6_capture(value)

    def test_malformed_capture(self):
        self.path.write_bytes(b"{broken\n")
        with self.assertRaises(TrafficEvidenceError):
            read_k6_capture(str(self.path))

    def test_duplicate_ids(self):
        self.path.write_bytes(
            encode([k6_point("req-1"), k6_point("req-1")])
        )
        with self.assertRaises(TrafficEvidenceError):
            read_k6_capture(str(self.path))


if __name__ == "__main__":
    unittest.main()
