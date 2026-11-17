"""Functional and adversarial tests for P15 synthetic traffic evidence."""

import copy
import unittest

from experiments.traffic_evidence_p15 import (
    TrafficEvidenceError,
    compare_traffic,
    summarize_traffic,
    validate_events,
)


def make_events(scenario, count, spacing_ms, sessions=1):
    return [
        {
            "time_ms": i * spacing_ms,
            "scenario": scenario,
            "path": "/api/data" if i % 2 else "/health",
            "status": 200,
            "session": f"user-{i % sessions}",
            "client_ip": "192.0.2.10",
        }
        for i in range(count)
    ]


class TestTrafficEvidenceP15(unittest.TestCase):

    def setUp(self):
        self.organic = make_events("organic", 20, 1000, 5)
        self.ddos = make_events("synthetic_ddos", 100, 50, 2)

    def test_organic_metrics(self):
        result = summarize_traffic(self.organic)
        self.assertEqual(result["request_count"], 20)
        self.assertEqual(result["unique_sessions"], 5)
        self.assertFalse(result["source_ip_separation_verified"])

    def test_rate_difference(self):
        result = compare_traffic(self.organic, self.ddos)
        self.assertGreater(result["rate_ratio"], 10)
        self.assertFalse(result["detector_classification_verified"])

    def test_nat_negative_control(self):
        rows = make_events("nat_negative_control", 20, 1000, 10)
        result = summarize_traffic(rows)
        self.assertEqual(result["unique_sessions"], 10)
        self.assertEqual(result["synthetic_ip_labels"], 1)
        self.assertFalse(result["source_ip_separation_verified"])

    def test_cache_control_not_real_cache(self):
        rows = make_events("cache_probe", 10, 500)
        result = summarize_traffic(rows)
        self.assertFalse(result["production_traffic_verified"])

    def test_ambiguous_not_classified(self):
        rows = make_events("synthetic_ambiguous", 10, 500)
        result = summarize_traffic(rows)
        self.assertFalse(result["detector_classification_verified"])

    def test_reject_empty(self):
        with self.assertRaises(TrafficEvidenceError):
            validate_events([])

    def test_reject_one_event(self):
        with self.assertRaises(TrafficEvidenceError):
            validate_events(self.organic[:1])

    def test_reject_unknown_field(self):
        rows = copy.deepcopy(self.organic)
        rows[0]["trusted"] = True
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_invalid_ip(self):
        rows = copy.deepcopy(self.organic)
        rows[0]["client_ip"] = "8.8.8.8"
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_forged_ip_string(self):
        rows = copy.deepcopy(self.organic)
        rows[0]["client_ip"] = "192.0.2.10, 8.8.8.8"
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_out_of_order(self):
        rows = copy.deepcopy(self.organic)
        rows[3]["time_ms"] = 0
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_zero_duration(self):
        rows = copy.deepcopy(self.organic)
        for row in rows:
            row["time_ms"] = 0
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_boolean_status(self):
        rows = copy.deepcopy(self.organic)
        rows[0]["status"] = True
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_nonfinite(self):
        rows = copy.deepcopy(self.organic)
        rows[0]["time_ms"] = float("nan")
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_invalid_scenario(self):
        rows = copy.deepcopy(self.organic)
        rows[0]["scenario"] = "production_ddos"
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_invalid_baseline(self):
        with self.assertRaises(TrafficEvidenceError):
            compare_traffic(self.ddos, self.organic)

    def test_reject_too_many_events(self):
        rows = make_events("organic", 2001, 1)
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)

    def test_reject_duplicate_key_equivalent(self):
        rows = copy.deepcopy(self.organic)
        rows[0]["session"] = None
        with self.assertRaises(TrafficEvidenceError):
            validate_events(rows)


if __name__ == "__main__":
    unittest.main()
