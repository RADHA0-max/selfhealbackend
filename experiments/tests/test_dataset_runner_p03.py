"""Tests for synthetic dataset evaluation."""

import json
import unittest
from pathlib import Path

from experiments.dataset_loader import load_dataset
from experiments.dataset_runner import run_dataset


DATASET_PATH = Path("experiments/datasets/diagnosis_p03_v1.json")


def dataset():
    return {
        "schema_version": 1,
        "dataset_type": "synthetic",
        "cases": list(load_dataset(DATASET_PATH)),
    }


def response(expected):
    return json.dumps({
        "category": expected["category"],
        "target": expected["target"],
        "confidence": 0.8,
        "summary": "Synthetic offline diagnosis.",
        "recommended_action": expected["recommended_action"],
    })


class TestDatasetRunner(unittest.TestCase):

    def test_all_correct(self):
        data = dataset()
        responses = {
            case["case_id"]: response(case["expected"])
            for case in data["cases"]
        }

        report = run_dataset(data, responses)

        self.assertEqual(report["requested"], 5)
        self.assertEqual(report["completed"], 5)
        self.assertEqual(report["valid_decision_rate"], 1.0)
        self.assertEqual(report["exact_match_rate"], 1.0)
        self.assertIsNone(report["recovery_success"])

    def test_valid_but_incorrect(self):
        data = dataset()
        responses = {
            case["case_id"]: response(case["expected"])
            for case in data["cases"]
        }

        first = data["cases"][0]["case_id"]
        responses[first] = response(data["cases"][1]["expected"])

        report = run_dataset(data, responses)

        self.assertEqual(report["valid_decision_rate"], 1.0)
        self.assertEqual(report["exact_match_rate"], 0.8)

    def test_invalid_json(self):
        data = dataset()
        responses = {
            case["case_id"]: response(case["expected"])
            for case in data["cases"]
        }

        first = data["cases"][0]["case_id"]
        responses[first] = "invalid-json"

        report = run_dataset(data, responses)

        self.assertEqual(report["completed"], 4)
        self.assertEqual(report["valid_decision_rate"], 0.8)
        self.assertEqual(
            report["results"][0]["failure_reason"],
            "invalid_json",
        )

    def test_missing_response_rejected(self):
        data = dataset()

        with self.assertRaises(ValueError):
            run_dataset(data, {})


if __name__ == "__main__":
    unittest.main()
