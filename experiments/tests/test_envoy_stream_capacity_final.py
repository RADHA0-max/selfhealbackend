"""Capacity and boundary tests for streaming Envoy evidence."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from experiments.envoy_stream_final import (
    extract_envoy_ids,
    reconcile_envoy_stream,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class EnvoyStreamCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "envoy.jsonl"

    def write_events(self, count):
        start = dt.datetime(
            2026, 11, 18, 12, 0, 0,
            tzinfo=dt.timezone.utc,
        )

        ids = []
        with self.path.open("wb") as stream:
            for index in range(count):
                request_id = (
                    f"offline-organic-vu-"
                    f"{index % 60 + 1}-iter-{index // 60}"
                )
                ids.append(request_id)

                timestamp = start + dt.timedelta(
                    milliseconds=index // 10
                )

                event = {
                    "timestamp": timestamp.isoformat(),
                    "client_ip": "172.20.0.10",
                    "method": "GET",
                    "path": "/ready",
                    "status": 200,
                    "duration_ms": 5,
                    "user_agent": "NanoClaw-Test",
                    "request_id": request_id,
                }

                stream.write(
                    json.dumps(event).encode("utf-8") + b"\n"
                )

        return ids

    def test_1200_requests(self):
        ids = self.write_events(1200)

        result = extract_envoy_ids(str(self.path))
        self.assertEqual(result["request_count"], 1200)

        reconciliation = reconcile_envoy_stream(
            str(self.path), ids
        )
        self.assertTrue(
            reconciliation["request_ids_match"]
        )

    def test_101_requests_single_trailing_event(self):
        self.write_events(101)
        result = extract_envoy_ids(str(self.path))
        self.assertEqual(result["request_count"], 101)

    def test_duplicate_key_rejected(self):
        self.write_events(2)

        raw = self.path.read_bytes()
        raw = raw.replace(
            b'"status": 200',
            b'"status": 200, "status": 503',
            1,
        )
        self.path.write_bytes(raw)

        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_ids(str(self.path))

    def test_out_of_order_rejected(self):
        self.write_events(2)

        lines = self.path.read_bytes().splitlines(
            keepends=True
        )

        first = json.loads(lines[0])
        second = json.loads(lines[1])

        second["timestamp"] = (
            "2026-11-18T11:59:59+00:00"
        )

        lines[1] = (
            json.dumps(second).encode("utf-8") + b"\n"
        )

        self.path.write_bytes(b"".join(lines))

        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_ids(str(self.path))


if __name__ == "__main__":
    unittest.main()
