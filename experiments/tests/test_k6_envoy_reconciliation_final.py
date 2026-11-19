import json
import unittest

from experiments.k6_envoy_reconciliation_final import reconcile_k6_envoy
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def k6_record(request_id):
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


def envoy_record(request_id):
    second = 1 if request_id == "req-2" else 0
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
    ).encode("utf-8")


class TestK6EnvoyReconciliationFinal(unittest.TestCase):

    def test_exact_match(self):
        report = reconcile_k6_envoy(
            encode([k6_record("req-1"), k6_record("req-2")]),
            encode([
                dict(envoy_record("req-2"),
                     timestamp="2026-11-17T00:00:00Z"),
                dict(envoy_record("req-1"),
                     timestamp="2026-11-17T00:00:01Z"),
            ]),
        )
        self.assertEqual(report["k6_manifest_request_count"], 2)
        self.assertFalse(report["runtime_origin_verified"])
        self.assertFalse(report["source_ip_verified"])
        self.assertFalse(report["envoy_capture_complete_verified"])

    def test_missing_envoy_request(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy(
                encode([k6_record("req-1"), k6_record("req-2")]),
                encode([envoy_record("req-1")]),
            )

    def test_unexpected_envoy_request(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy(
                encode([k6_record("req-1")]),
                encode([envoy_record("req-1"), envoy_record("req-3")]),
            )

    def test_duplicate_k6_id(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy(
                encode([k6_record("req-1"), k6_record("req-1")]),
                encode([envoy_record("req-1")]),
            )

    def test_duplicate_envoy_id(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy(
                encode([k6_record("req-1")]),
                encode([envoy_record("req-1"), envoy_record("req-1")]),
            )

    def test_malformed_k6(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy(
                b"{broken\n",
                encode([envoy_record("req-1")]),
            )

    def test_malformed_envoy(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy(
                encode([k6_record("req-1")]),
                b"{broken\n",
            )

    def test_wrong_input_types(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy("not bytes", b"")
        with self.assertRaises(TrafficEvidenceError):
            reconcile_k6_envoy(b"", "not bytes")


if __name__ == "__main__":
    unittest.main()
