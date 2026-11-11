"""Offline integration contract tests for P03."""

import json
import unittest

from agent.diagnosis import DiagnosisError, diagnose
from experiments.offline_rpc import OfflineRPC
from experiments.runner import run_experiment
from testbed.fixtures import build_fixtures


class TestP03Integration(unittest.TestCase):

    def setUp(self):
        self.case = build_fixtures()[0]

    def valid_response(self):
        return json.dumps({
            "category": self.case.expected_category,
            "target": self.case.expected_target,
            "confidence": 0.9,
            "summary": "Offline integration test.",
            "recommended_action": self.case.expected_action,
        })

    def test_valid_diagnosis_contract(self):
        rpc = OfflineRPC(self.valid_response())

        result = diagnose(rpc, self.case.evidence)

        self.assertEqual(
            result.category,
            self.case.expected_category,
        )
        self.assertEqual(
            result.recommended_action,
            self.case.expected_action,
        )
        self.assertEqual(len(rpc.calls), 1)

    def test_invalid_json_is_rejected(self):
        rpc = OfflineRPC("not-json")

        with self.assertRaises(DiagnosisError):
            diagnose(rpc, self.case.evidence)

    def test_runner_records_invalid_decision(self):
        result = run_experiment(
            (self.case,),
            OfflineRPC("not-json"),
        )

        self.assertEqual(result["requested"], 1)
        self.assertEqual(result["completed"], 0)
        self.assertEqual(
            result["status_counts"]["invalid_decision"],
            1,
        )

    def test_runner_scores_valid_decision(self):
        result = run_experiment(
            (self.case,),
            OfflineRPC(self.valid_response()),
        )

        self.assertEqual(result["requested"], 1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["exact_match_rate"], 1.0)

    def test_offline_run_never_claims_recovery(self):
        result = run_experiment(
            (self.case,),
            OfflineRPC(self.valid_response()),
        )

        self.assertIsNone(result["recovery_success"])
        self.assertEqual(result["mode"], "synthetic_offline")


if __name__ == "__main__":
    unittest.main()
