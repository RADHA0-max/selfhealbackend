"""Regression tests for validity versus diagnosis accuracy."""

import unittest

from experiments.scoring import score_results


class TestScoringValidity(unittest.TestCase):

    @staticmethod
    def row(status, correct=False):
        return {
            "status": status,
            "category_correct": correct,
            "target_correct": correct,
            "action_correct": correct,
        }

    def test_validity_and_accuracy_have_different_denominators(self):
        rows = (
            [self.row("ok", True) for _ in range(70)]
            + [self.row("ok", False) for _ in range(20)]
            + [self.row("invalid_decision") for _ in range(10)]
        )

        report = score_results(rows)

        self.assertEqual(report["requested"], 100)
        self.assertEqual(report["completed"], 90)
        self.assertEqual(report["exact_match_rate"], 0.7)
        self.assertEqual(report["valid_decision_rate"], 0.9)
        self.assertAlmostEqual(
            report["correct_given_valid_rate"],
            70 / 90,
        )

    def test_no_valid_decisions(self):
        report = score_results([
            self.row("invalid_decision"),
            self.row("agent_error"),
        ])

        self.assertEqual(report["valid_decision_rate"], 0.0)
        self.assertIsNone(report["correct_given_valid_rate"])

    def test_empty_dataset(self):
        report = score_results([])

        self.assertIsNone(report["valid_decision_rate"])
        self.assertIsNone(report["correct_given_valid_rate"])

    def test_existing_metrics_preserved(self):
        report = score_results([
            self.row("ok", True),
            self.row("invalid_decision"),
        ])

        self.assertEqual(report["requested"], 2)
        self.assertEqual(report["completed"], 1)
        self.assertEqual(report["completion_rate"], 0.5)
        self.assertEqual(report["failure_rate"], 0.5)
        self.assertEqual(report["exact_match_rate"], 0.5)
        self.assertIsNone(report["recovery_success"])
        self.assertEqual(report["mode"], "synthetic_offline")


if __name__ == "__main__":
    unittest.main()
