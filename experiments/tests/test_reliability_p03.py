"""Deterministic 100-case offline diagnosis reliability tests."""

import json
import unittest

from agent.diagnosis import DiagnosisError, diagnose
from experiments.offline_rpc import OfflineRPC
from experiments.scoring import score_results


class TestOfflineReliability(unittest.TestCase):

    @staticmethod
    def valid_response():
        return json.dumps({
            "category": "service_failure",
            "target": "api",
            "confidence": 0.9,
            "summary": "Synthetic API failure.",
            "recommended_action": "investigate_api",
        })

    @staticmethod
    def evidence(index):
        return {
            "signal_id": f"synthetic-{index:03d}",
            "probes": {
                "api": {"status": 503},
            },
        }

    def test_one_hundred_case_accounting(self):
        rows = []

        for index in range(100):
            response = (
                self.valid_response()
                if index < 80
                else "invalid-json"
            )

            rpc = OfflineRPC(response)

            row = {
                "case_id": f"synthetic-{index:03d}",
                "status": "invalid_decision",
                "category_correct": False,
                "target_correct": False,
                "action_correct": False,
            }

            try:
                diagnosis = diagnose(
                    rpc,
                    self.evidence(index),
                )
            except DiagnosisError:
                pass
            else:
                row.update(
                    status="ok",
                    category_correct=(
                        diagnosis.category == "service_failure"
                    ),
                    target_correct=(
                        diagnosis.target == "api"
                    ),
                    action_correct=(
                        diagnosis.recommended_action
                        == "investigate_api"
                    ),
                )

            rows.append(row)

        report = score_results(rows)

        self.assertEqual(report["requested"], 100)
        self.assertEqual(report["completed"], 80)
        self.assertEqual(
            report["status_counts"]["invalid_decision"],
            20,
        )
        self.assertEqual(report["completion_rate"], 0.8)
        self.assertEqual(report["failure_rate"], 0.2)
        self.assertEqual(report["exact_match_rate"], 0.8)
        self.assertIsNone(report["recovery_success"])
        self.assertEqual(report["mode"], "synthetic_offline")


if __name__ == "__main__":
    unittest.main()
