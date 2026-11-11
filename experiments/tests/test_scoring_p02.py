"""P02 regression tests for synthetic experiment metrics."""

import unittest

from experiments.scoring import score_results


class ScoringP02Tests(unittest.TestCase):

    def test_mixed_results(self):
        rows = [
            {
                "status": "ok",
                "category_correct": True,
                "target_correct": True,
                "action_correct": True,
            },
            {
                "status": "ok",
                "category_correct": True,
                "target_correct": False,
                "action_correct": True,
            },
            {
                "status": "invalid_decision",
                "category_correct": False,
                "target_correct": False,
                "action_correct": False,
            },
            {
                "status": "agent_error",
                "category_correct": False,
                "target_correct": False,
                "action_correct": False,
            },
        ]

        result = score_results(rows)

        self.assertEqual(result["requested"], 4)
        self.assertEqual(result["completed"], 2)
        self.assertEqual(result["completion_rate"], 0.5)
        self.assertEqual(result["failure_rate"], 0.5)
        self.assertEqual(result["exact_match_rate"], 0.25)

        self.assertEqual(
            result["status_counts"],
            {
                "ok": 2,
                "invalid_decision": 1,
                "agent_error": 1,
            },
        )

        self.assertEqual(result["scores"]["category_correct"], 0.5)
        self.assertEqual(result["scores"]["target_correct"], 0.25)
        self.assertEqual(result["scores"]["action_correct"], 0.5)

        self.assertIsNone(result["recovery_success"])
        self.assertEqual(result["mode"], "synthetic_offline")

    def test_empty_results(self):
        result = score_results([])

        self.assertEqual(result["requested"], 0)
        self.assertEqual(result["completed"], 0)
        self.assertIsNone(result["completion_rate"])
        self.assertIsNone(result["failure_rate"])
        self.assertIsNone(result["exact_match_rate"])

        self.assertEqual(
            result["status_counts"],
            {
                "ok": 0,
                "invalid_decision": 0,
                "agent_error": 0,
            },
        )

    def test_partial_match_is_not_exact(self):
        rows = [{
            "status": "ok",
            "category_correct": True,
            "target_correct": True,
            "action_correct": False,
        }]

        result = score_results(rows)

        self.assertEqual(result["completion_rate"], 1.0)
        self.assertEqual(result["failure_rate"], 0.0)
        self.assertEqual(result["exact_match_rate"], 0.0)

    def test_failed_case_cannot_count_as_exact(self):
        rows = [{
            "status": "invalid_decision",
            "category_correct": True,
            "target_correct": True,
            "action_correct": True,
        }]

        result = score_results(rows)

        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["exact_match_rate"], 0.0)
        self.assertEqual(result["failure_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
