import json
import tempfile
import unittest
from pathlib import Path

from experiments.k6_stream_reconciliation_final import (
    reconcile_k6_stream_with_envoy,
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


class TestK6StreamReconciliationFinal(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "k6.jsonl"
        self.ids = ["runA-organic-vu-1-iter-0",
                    "runA-organic-vu-2-iter-0"]
        self.path.write_bytes(encode([
            {"type": "Metric", "metric": "http_reqs", "data": {}},
            k6_point(self.ids[0]),
            {"type": "Point", "metric": "http_reqs",
             "data": {"value": 1}},
            k6_point(self.ids[1]),
        ]))

    def test_exact_match(self):
        envoy = encode([
            envoy_record(self.ids[1], 0),
            envoy_record(self.ids[0], 1),
        ])
        result = reconcile_k6_stream_with_envoy(str(self.path), envoy)
        self.assertEqual(result["k6_request_count"], 2)
        self.assertFalse(result["runtime_origin_verified"])
        self.assertFalse(result["source_ip_verified"])

    def test_missing_envoy_id(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_stream_with_envoy(
                str(self.path),
                encode([envoy_record(self.ids[0], 0)]),
            )

    def test_unexpected_envoy_id(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_stream_with_envoy(
                str(self.path),
                encode([
                    envoy_record(self.ids[0], 0),
                    envoy_record("other-run-id", 1),
                ]),
            )

    def test_malformed_envoy(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_stream_with_envoy(str(self.path), b"{broken\n")

    def test_malformed_k6(self):
        self.path.write_bytes(b"{broken\n")
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_stream_with_envoy(
                str(self.path),
                encode([
                    envoy_record(self.ids[0], 0),
                    envoy_record(self.ids[1], 1),
                ]),
            )


if __name__ == "__main__":
    unittest.main()
