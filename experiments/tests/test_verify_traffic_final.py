"""End-to-end offline verification of k6 and Envoy JSONL evidence."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from experiments.verify_traffic_final import verify
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class VerifyTrafficTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)
        self.k6 = root / "k6.jsonl"
        self.envoy = root / "envoy.jsonl"
        self.run_id = "offline-test"

    def write_fixture(self, count=1200, missing=None, duplicate=False):
        start = dt.datetime(
            2026, 11, 18, 12, 0, 0,
            tzinfo=dt.timezone.utc,
        )

        k6_lines = []
        envoy_lines = []

        for index in range(count):
            vu = index % 60 + 1
            iteration = index // 60

            request_id = (
                f"{self.run_id}-organic-vu-{vu}-iter-{iteration}"
            )

            k6_record = {
                "type": "Point",
                "metric": "nanoclaw_request_manifest",
                "data": {
                    "time": start.isoformat(),
                    "value": 1,
                    "tags": {
                        "request_id": request_id,
                        "workload": "organic_60vu",
                    },
                },
            }

            k6_lines.append(
                json.dumps(k6_record).encode() + b"\n"
            )

            if index == missing:
                continue

            if duplicate and index == count - 1:
                request_id = (
                    f"{self.run_id}-organic-vu-1-iter-0"
                )

            timestamp = start + dt.timedelta(
                milliseconds=index // 10
            )

            envoy_record = {
                "timestamp": timestamp.isoformat(),
                "client_ip": "172.20.0.10",
                "method": "GET",
                "path": "/ready",
                "status": 200,
                "duration_ms": 5,
                "user_agent": "NanoClaw-Test",
                "request_id": request_id,
            }

            envoy_lines.append(
                json.dumps(envoy_record).encode() + b"\n"
            )

        self.k6.write_bytes(b"".join(k6_lines))
        self.envoy.write_bytes(b"".join(envoy_lines))

    def test_1200_request_end_to_end(self):
        self.write_fixture()
        result = verify(
            str(self.k6),
            str(self.envoy),
            self.run_id,
        )
        self.assertEqual(result["k6_request_count"], 1200)
        self.assertTrue(result["request_ids_match"])
        self.assertFalse(result["runtime_origin_verified"])
        self.assertFalse(result["source_ip_verified"])

    def test_missing_envoy_request_rejected(self):
        self.write_fixture(count=20, missing=7)
        with self.assertRaises(TrafficEvidenceError):
            verify(str(self.k6), str(self.envoy), self.run_id)

    def test_duplicate_envoy_request_rejected(self):
        self.write_fixture(count=20, duplicate=True)
        with self.assertRaises(TrafficEvidenceError):
            verify(str(self.k6), str(self.envoy), self.run_id)

    def test_wrong_run_id_rejected(self):
        self.write_fixture(count=20)
        with self.assertRaises(TrafficEvidenceError):
            verify(str(self.k6), str(self.envoy), "other-run")

    def test_invalid_run_id_rejected(self):
        self.write_fixture(count=20)
        with self.assertRaises(TrafficEvidenceError):
            verify(str(self.k6), str(self.envoy), "../unsafe")


if __name__ == "__main__":
    unittest.main()
