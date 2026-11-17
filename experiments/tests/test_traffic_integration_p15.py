"""Offline integration of P15 synthetic and Envoy traffic measurements."""

import datetime as dt
import json
import unittest

from experiments.envoy_traffic_p15 import summarize_envoy_jsonl
from experiments.traffic_evidence_p15 import compare_traffic


def synthetic_events(scenario, count, gap_ms, sessions):
    return [
        {
            "time_ms": i * gap_ms,
            "scenario": scenario,
            "path": "/api/data",
            "status": 200,
            "session": f"user-{i % sessions}",
            "client_ip": "192.0.2.10",
        }
        for i in range(count)
    ]


def envoy_log(count, gap_ms, ip="192.0.2.10"):
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    records = []

    for i in range(count):
        records.append({
            "timestamp": (
                start + dt.timedelta(milliseconds=i * gap_ms)
            ).isoformat(),
            "client_ip": ip,
            "method": "GET",
            "path": "/api/data",
            "status": "200",
            "duration_ms": "12",
            "user_agent": "NanoClaw-Offline-Fixture/1.0",
            "request_id": f"req-{i}",
        })

    return (
        "\n".join(json.dumps(row) for row in records) + "\n"
    ).encode("utf-8")


class TestTrafficIntegrationP15(unittest.TestCase):

    def test_synthetic_rate_comparison(self):
        baseline = synthetic_events("organic", 20, 1000, 5)
        candidate = synthetic_events(
            "synthetic_ddos", 100, 50, 2
        )

        result = compare_traffic(baseline, candidate)

        self.assertGreater(result["rate_ratio"], 10)
        self.assertFalse(
            result["detector_classification_verified"]
        )

    def test_envoy_rate_comparison(self):
        baseline = summarize_envoy_jsonl(envoy_log(20, 1000))
        candidate = summarize_envoy_jsonl(envoy_log(100, 50))

        self.assertGreater(
            candidate["requests_per_second"],
            baseline["requests_per_second"] * 10,
        )

    def test_nat_shared_ip(self):
        result = summarize_envoy_jsonl(
            envoy_log(20, 100)
        )

        self.assertEqual(
            result["unique_observed_ip_values"], 1
        )
        self.assertFalse(
            result["source_ip_separation_verified"]
        )

    def test_no_production_claims(self):
        result = summarize_envoy_jsonl(
            envoy_log(20, 100)
        )

        self.assertFalse(
            result["detector_classification_verified"]
        )
        self.assertFalse(
            result["production_traffic_verified"]
        )
        self.assertFalse(
            result["mitigation_executed"]
        )


if __name__ == "__main__":
    unittest.main()
