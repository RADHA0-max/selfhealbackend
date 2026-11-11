"""Offline evaluation of diverse diagnosis outcomes."""

import json
import unittest

from agent.diagnosis import diagnose
from experiments.offline_rpc import OfflineRPC
from experiments.scoring import score_results


CASES = (
    ("service_failure", "api", "investigate_api"),
    ("dependency_failure", "database", "investigate_database"),
    ("latency", "worker", "investigate_latency"),
    ("resource_exhaustion", "worker", "investigate_resources"),
    ("unknown", "unknown", "collect_more_evidence"),
)


def response(category, target, action):
    return json.dumps({
        "category": category,
        "target": target,
        "confidence": 0.8,
        "summary": "Synthetic diagnosis response.",
        "recommended_action": action,
    })


class TestDiverseDiagnoses(unittest.TestCase):

    def test_multiple_correct_categories(self):
        rows = []

        for index, (category, target, action) in enumerate(CASES):
            result = diagnose(
                OfflineRPC(response(category, target, action)),
                {"signal_id": f"diverse-{index}"},
            )

            rows.append({
                "status": "ok",
                "category_correct": result.category == category,
                "target_correct": result.target == target,
                "action_correct": result.recommended_action == action,
            })

        report = score_results(rows)

        self.assertEqual(report["requested"], 5)
        self.assertEqual(report["completed"], 5)
        self.assertEqual(report["exact_match_rate"], 1.0)

    def test_valid_but_incorrect_diagnosis(self):
        expected = CASES[1]

        result = diagnose(
            OfflineRPC(response(
                "service_failure",
                "api",
                "investigate_api",
            )),
            {"signal_id": "incorrect-case"},
        )

        row = {
            "status": "ok",
            "category_correct": result.category == expected[0],
            "target_correct": result.target == expected[1],
            "action_correct": result.recommended_action == expected[2],
        }

        report = score_results([row])

        self.assertEqual(report["valid_decision_rate"], 1.0)
        self.assertEqual(report["exact_match_rate"], 0.0)
        self.assertEqual(report["correct_given_valid_rate"], 0.0)

    def test_unknown_category_is_valid(self):
        result = diagnose(
            OfflineRPC(response(
                "unknown",
                "unknown",
                "collect_more_evidence",
            )),
            {"signal_id": "unknown-case"},
        )

        self.assertEqual(result.category, "unknown")
        self.assertEqual(
            result.recommended_action,
            "collect_more_evidence",
        )


if __name__ == "__main__":
    unittest.main()
