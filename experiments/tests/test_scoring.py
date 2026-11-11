"""Offline scoring tests."""

import unittest

from experiments.scoring import score_results


class TestScoring(unittest.TestCase):

    def test_empty_results(self):
        report = score_results([])
        self.assertEqual(report["requested"], 0)
        self.assertIsNone(report["scores"]["category_correct"])

    def test_failures_count_in_denominator(self):
        rows = [
            {
                "status": "ok",
                "category_correct": True,
                "target_correct": True,
                "action_correct": True,
            },
            {
                "status": "invalid_decision",
                "category_correct": False,
                "target_correct": False,
                "action_correct": False,
            },
        ]

        report = score_results(rows)

        self.assertEqual(report["requested"], 2)
        self.assertEqual(report["completed"], 1)
        self.assertEqual(report["scores"]["category_correct"], 0.5)
        self.assertIsNone(report["recovery_success"])


if __name__ == "__main__":
    unittest.main()
