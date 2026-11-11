"""Regression tests for offline runner failure reasons."""

import json
import unittest

from experiments.offline_rpc import OfflineRPC
from experiments.runner import run_experiment
from testbed.fixtures import build_fixtures


class TestRunnerFailureReasons(unittest.TestCase):

    def setUp(self):
        self.case = build_fixtures()[0]

    def run_response(self, response):
        result = run_experiment(
            (self.case,),
            OfflineRPC(response),
        )
        return result["results"][0], result

    def test_invalid_json(self):
        row, result = self.run_response("invalid-json")

        self.assertEqual(row["status"], "invalid_decision")
        self.assertEqual(row["failure_reason"], "invalid_json")
        self.assertEqual(
            result["status_counts"]["invalid_decision"],
            1,
        )

    def test_invalid_schema(self):
        row, _ = self.run_response("{}")

        self.assertEqual(row["status"], "invalid_decision")
        self.assertEqual(row["failure_reason"], "invalid_schema")

    def test_valid_response(self):
        case = self.case

        response = json.dumps({
            "category": case.expected_category,
            "target": case.expected_target,
            "confidence": 0.9,
            "summary": "Synthetic offline diagnosis.",
            "recommended_action": case.expected_action,
        })

        row, result = self.run_response(response)

        self.assertEqual(row["status"], "ok")
        self.assertIsNone(row["failure_reason"])
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["exact_match_rate"], 1.0)

    def test_existing_metrics_preserved(self):
        _, result = self.run_response("invalid-json")

        self.assertEqual(result["requested"], 1)
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["failure_rate"], 1.0)
        self.assertIsNone(result["recovery_success"])


if __name__ == "__main__":
    unittest.main()
