import json
import unittest
from datetime import datetime, timedelta, timezone

from experiments.traffic_evidence_p15 import TrafficEvidenceError
from testbed.experiments.p01_evidence_adapter import normalize_envoy


RUN_ID = "p01_cache_run001"
class CacheEvidenceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cls.rows = [
            {
                "timestamp": (
                    start + timedelta(milliseconds=i * 100)
                ).isoformat(),
                "client_ip": "172.25.0.4",
                "method": "GET",
                "path": (
                    f"/api/data?cache_key={RUN_ID}-1-{i}"
                ),
                "status": 200,
                "duration_ms": 1,
                "user_agent": "NanoClaw-Cache-P01/1.0",
                "request_id": (
                    f"{RUN_ID}-cache-vu-1-iter-{i}"
                ),
            }
            for i in range(50)
        ]

    def encode(self, rows):
        return (
            "\n".join(json.dumps(row) for row in rows) + "\n"
        ).encode()

    def test_valid_cache_evidence(self):
        events = normalize_envoy(self.encode(self.rows), RUN_ID)
        self.assertEqual(len(events), 50)
        self.assertTrue(all(e["workload"] == "p01_cache" for e in events))

    def test_unknown_query_parameter_rejected(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["path"] = "/api/data?unknown=1"
        with self.assertRaises((ValueError, TrafficEvidenceError)):
            normalize_envoy(self.encode(rows), RUN_ID)

    def test_non_cache_query_rejected(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["request_id"] = RUN_ID + "-ddos-vu-1-iter-0"
        with self.assertRaises((ValueError, TrafficEvidenceError)):
            normalize_envoy(self.encode(rows), RUN_ID)

    def test_foreign_run_rejected(self):
        with self.assertRaises((ValueError, TrafficEvidenceError)):
            normalize_envoy(self.encode(self.rows), "foreign_run")

    def test_duplicate_json_key_rejected(self):
        lines = self.encode(self.rows).decode().splitlines()
        lines[0] = lines[0][:-1] + ',"path":"/api/data"}'
        with self.assertRaises((ValueError, TrafficEvidenceError)):
            normalize_envoy(("\n".join(lines) + "\n").encode(), RUN_ID)

    def test_malformed_cache_key_rejected(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["path"] = "/api/data?cache_key=../../etc/passwd"
        with self.assertRaises((ValueError, TrafficEvidenceError)):
            normalize_envoy(self.encode(rows), RUN_ID)

    def test_extra_cache_parameter_rejected(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["path"] += "&admin=true"
        with self.assertRaises((ValueError, TrafficEvidenceError)):
            normalize_envoy(self.encode(rows), RUN_ID)


if __name__ == "__main__":
    unittest.main()
