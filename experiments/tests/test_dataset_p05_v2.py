"""Regression checks for the evidence-calibrated P05 dataset."""

import unittest
from pathlib import Path

from experiments.dataset_loader import load_dataset


DATASET = (
    Path(__file__).resolve().parents[1]
    / "datasets"
    / "diagnosis_p05_v2.json"
)


class P05DatasetTests(unittest.TestCase):
    def test_dataset_loads(self):
        cases = load_dataset(DATASET)
        self.assertEqual(len(cases), 5)

    def test_labels_match_available_evidence(self):
        cases = load_dataset(DATASET)

        for case in cases:
            signal = case["signal"]
            expected = case["expected"]

            self.assertEqual(
                expected["target"],
                signal["target"],
            )

            self.assertNotIn(
                expected["category"],
                {"dependency_failure", "resource_exhaustion"},
            )

            if expected["category"] == "latency":
                self.assertIn("latency_ms", signal)
                self.assertGreater(signal["latency_ms"], 0)

            if signal["status"] == 200:
                self.assertEqual(expected["category"], "unknown")
                self.assertEqual(
                    expected["recommended_action"],
                    "collect_more_evidence",
                )


if __name__ == "__main__":
    unittest.main()
