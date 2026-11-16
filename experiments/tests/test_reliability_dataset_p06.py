"""Offline tests for the P06 repeated-prompt reliability dataset."""

import unittest

from experiments.dataset_loader import validate_dataset
from experiments.reliability_dataset_p06 import build_reliability_dataset


class ReliabilityDatasetTests(unittest.TestCase):

    def test_builds_exactly_100_valid_cases(self):
        dataset = build_reliability_dataset()
        cases = validate_dataset(dataset)

        self.assertEqual(len(cases), 100)
        self.assertEqual(len({c["case_id"] for c in cases}), 100)

    def test_preserves_signal_identity(self):
        dataset = build_reliability_dataset()

        for case in dataset["cases"]:
            self.assertEqual(
                case["case_id"],
                case["signal"]["signal_id"],
            )

    def test_is_deterministic(self):
        first = build_reliability_dataset()
        second = build_reliability_dataset()

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
