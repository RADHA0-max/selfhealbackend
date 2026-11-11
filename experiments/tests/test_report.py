"""Tests for deterministic offline experiment reporting."""

import json
import tempfile
import unittest
from pathlib import Path

from experiments.report import generate_report, write_report


class TestExperimentReport(unittest.TestCase):

    def test_all_six_fixtures_processed(self):
        report = generate_report()

        self.assertEqual(report["requested"], 6)
        self.assertEqual(report["completed"], 6)
        self.assertEqual(len(report["results"]), 6)

    def test_fixture_replay_scores(self):
        report = generate_report()

        self.assertEqual(
            report["scores"],
            {
                "category_correct": 1.0,
                "target_correct": 1.0,
                "action_correct": 1.0,
            },
        )

    def test_no_live_recovery_claims(self):
        report = generate_report()

        self.assertEqual(report["evaluation"], "fixture_replay")
        self.assertFalse(report["model_inference_performed"])
        self.assertFalse(report["recovery_attempted"])
        self.assertIsNone(report["recovery_success"])
        self.assertEqual(report["mode"], "synthetic_offline")

    def test_report_is_deterministic(self):
        self.assertEqual(generate_report(), generate_report())

    def test_written_report_matches_generated_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"

            expected = write_report(path)
            actual = json.loads(path.read_text())

            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
