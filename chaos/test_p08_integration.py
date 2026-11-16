"""Offline integration of testbed faults and recovery experiment evaluation."""

import unittest

from chaos.recorded_experiment import evaluate_experiment
from chaos.recovery_timeline import evaluate_timeline
from testbed.app.faults import FaultController


def simulated_events(mode, count=9):
    controller = FaultController(mode)
    return [
        {
            "time_ms": index * 1000,
            "target": "api",
            "status": controller.next_observation().status,
            "latency_ms": 250 if mode == "latency" else 10,
        }
        for index in range(count)
    ]


class P08IntegrationTests(unittest.TestCase):

    def test_recovering_scenario(self):
        result = evaluate_timeline(simulated_events("recovering"))
        self.assertEqual(result["observation_outcome"], "SUCCESS")
        self.assertFalse(result["recovery_attributed_to_agent"])

    def test_regression_scenario(self):
        result = evaluate_timeline(simulated_events("regression"))
        self.assertEqual(result["observation_outcome"], "FAILED")
        self.assertGreaterEqual(result["regression_count"], 1)

    def test_outage_scenario(self):
        result = evaluate_timeline(simulated_events("outage"))
        self.assertEqual(result["observation_outcome"], "FAILED")

    def test_latency_threshold(self):
        result = evaluate_timeline(
            simulated_events("latency"),
            healthy_latency_ms=100,
        )
        self.assertEqual(result["observation_outcome"], "FAILED")

    def test_healthy_negative_control(self):
        result = evaluate_timeline(simulated_events("healthy"))
        self.assertEqual(result["observation_outcome"], "INCONCLUSIVE")

    def test_experiment_pipeline(self):
        cases = [
            ("recovery", "recovering", "service_failure"),
            ("regression", "regression", "intermittent_failure"),
            ("outage", "outage", "service_failure"),
            ("control", "healthy", "negative_control"),
        ]

        data = {
            "schema_version": 1,
            "experiment_id": "p08-integrated-offline",
            "scenarios": [
                {
                    "scenario_id": identifier,
                    "kind": kind,
                    "events": simulated_events(mode),
                }
                for identifier, mode, kind in cases
            ],
        }

        report = evaluate_experiment(data)

        self.assertEqual(report["scenario_count"], 4)
        self.assertEqual(report["outcome_counts"], {
            "SUCCESS": 1,
            "FAILED": 2,
            "INCONCLUSIVE": 1,
        })
        self.assertFalse(report["mitigation_executed"])
        self.assertFalse(report["recovery_attributed_to_agent"])


if __name__ == "__main__":
    unittest.main()
