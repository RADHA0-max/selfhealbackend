"""Tests for versioned synthetic diagnosis datasets."""

import copy
import unittest
from pathlib import Path

from experiments.dataset_loader import (
    DatasetValidationError,
    load_dataset,
    validate_dataset,
)


DATASET = Path("experiments/datasets/diagnosis_p03_v1.json")


class TestDataset(unittest.TestCase):

    def test_checked_in_dataset(self):
        cases = load_dataset(DATASET)
        self.assertEqual(len(cases), 5)
        self.assertEqual(len({case["case_id"] for case in cases}), 5)

    def test_duplicate_case_id_rejected(self):
        cases = load_dataset(DATASET)
        raw = {
            "schema_version": 1,
            "dataset_type": "synthetic",
            "cases": [copy.deepcopy(cases[0]), copy.deepcopy(cases[0])],
        }
        with self.assertRaises(DatasetValidationError):
            validate_dataset(raw)

    def test_unknown_expected_category_rejected(self):
        cases = load_dataset(DATASET)
        bad = copy.deepcopy(cases[0])
        bad["expected"]["category"] = "execute_shell"
        with self.assertRaises(DatasetValidationError):
            validate_dataset({
                "schema_version": 1,
                "dataset_type": "synthetic",
                "cases": [bad],
            })

    def test_non_string_expected_labels_rejected(self):
        cases = load_dataset(DATASET)

        for field in (
            "category",
            "target",
            "recommended_action",
        ):
            with self.subTest(field=field):
                bad = copy.deepcopy(cases[0])
                bad["expected"][field] = ["invalid"]

                with self.assertRaises(DatasetValidationError):
                    validate_dataset({
                        "schema_version": 1,
                        "dataset_type": "synthetic",
                        "cases": [bad],
                    })

    def test_signal_id_mismatch_rejected(self):
        cases = load_dataset(DATASET)
        bad = copy.deepcopy(cases[0])
        bad["signal"]["signal_id"] = "different-id"
        with self.assertRaises(DatasetValidationError):
            validate_dataset({
                "schema_version": 1,
                "dataset_type": "synthetic",
                "cases": [bad],
            })


if __name__ == "__main__":
    unittest.main()
