"""Offline synthetic controls; candidate names are not attack labels."""

import unittest

from experiments.traffic_controls_p16 import evaluate_controls
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def events(scenario, count, gap, sessions=5, ips=1):
    return [
        {
            "time_ms": i * gap,
            "scenario": scenario,
            "path": "/api/data",
            "status": 200,
            "session": f"session-{i % sessions}",
            "client_ip": f"192.0.2.{10 + i % ips}",
        }
        for i in range(count)
    ]


class TestTrafficControlsP16(unittest.TestCase):

    def setUp(self):
        self.organic = events("organic", 20, 1000)

    def test_high_rate_is_not_attack_classification(self):
        report = evaluate_controls(
            self.organic,
            {"burst": events("synthetic_ddos", 100, 50)},
        )
        burst = report["candidates"]["burst"]
        self.assertGreater(burst["rate_ratio"], 10)
        self.assertEqual(
            burst["attack_classification"], "not_evaluated"
        )

    def test_shared_synthetic_ip_not_authenticated(self):
        report = evaluate_controls(
            self.organic,
            {"nat": events("organic", 60, 100, 30, 1)},
        )
        nat = report["candidates"]["nat"]
        self.assertEqual(nat["synthetic_ip_labels"], 1)
        self.assertEqual(nat["unique_sessions"], 30)
        self.assertFalse(nat["source_ip_separation_verified"])

    def test_repetitive_requests_not_attack_classification(self):
        report = evaluate_controls(
            self.organic,
            {"organic": events("organic", 40, 100)},
        )
        self.assertEqual(
            report["candidates"]["organic"]["attack_classification"],
            "not_evaluated",
        )

    def test_no_production_claims(self):
        report = evaluate_controls(
            self.organic,
            {"organic": events("organic", 20, 1000)},
        )
        self.assertFalse(report["detector_classification_verified"])
        self.assertFalse(report["production_traffic_verified"])
        self.assertFalse(report["mitigation_executed"])

    def test_reject_mixed_baseline(self):
        baseline = events("organic", 20, 1000)
        baseline[1]["scenario"] = "synthetic_ddos"

        with self.assertRaises(TrafficEvidenceError):
            evaluate_controls(
                baseline,
                {"burst": events("synthetic_ddos", 20, 100)},
            )

    def test_reject_mixed_candidate(self):
        candidate = events("organic", 20, 100)
        candidate[1]["scenario"] = "synthetic_ddos"

        with self.assertRaises(TrafficEvidenceError):
            evaluate_controls(
                self.organic,
                {"mixed": candidate},
            )

    def test_reject_invalid_candidate_name(self):
        with self.assertRaises(TrafficEvidenceError):
            evaluate_controls(
                self.organic,
                {"../unsafe": events("organic", 20, 100)},
            )

    def test_reject_too_many_candidates(self):
        candidates = {
            f"case-{i}": events("organic", 20, 100)
            for i in range(11)
        }

        with self.assertRaises(TrafficEvidenceError):
            evaluate_controls(self.organic, candidates)

    def test_report_scenario_provenance(self):
        report = evaluate_controls(
            self.organic,
            {"nat": events("organic", 20, 100)},
        )

        self.assertEqual(
            report["candidates"]["nat"]["scenario"],
            "organic",
        )
        self.assertEqual(
            report["evidence_source"],
            "synthetic_traffic_controls",
        )

    def test_reject_invalid_baseline(self):
        with self.assertRaises(TrafficEvidenceError):
            evaluate_controls(
                events("synthetic_ddos", 20, 1000),
                {"burst": events("synthetic_ddos", 20, 100)},
            )

    def test_reject_empty_candidates(self):
        with self.assertRaises(TrafficEvidenceError):
            evaluate_controls(self.organic, {})

    def test_reject_malformed_candidate(self):
        with self.assertRaises(TrafficEvidenceError):
            evaluate_controls(self.organic, {"bad": [{"invalid": True}]})


if __name__ == "__main__":
    unittest.main()
