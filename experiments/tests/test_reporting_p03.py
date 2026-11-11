"""Tests for deterministic synthetic evaluation reports."""

import json
import unittest
from pathlib import Path

from experiments.dataset_loader import load_dataset
from experiments.dataset_runner import run_dataset
from experiments.reporting import build_report


PATH = Path("experiments/datasets/diagnosis_p03_v1.json")


def evaluation():
    cases = list(load_dataset(PATH))
    responses = {}

    for case in cases:
        expected = case["expected"]
        responses[case["case_id"]] = json.dumps({
            "category": expected["category"],
            "target": expected["target"],
            "confidence": 0.8,
            "summary": "Synthetic offline response.",
            "recommended_action": expected["recommended_action"],
        })

    return run_dataset({
        "schema_version": 1,
        "dataset_type": "synthetic",
        "cases": cases,
    }, responses)


class TestReporting(unittest.TestCase):

    def test_deterministic_report(self):
        result = evaluation()

        first = build_report(PATH, result)
        second = build_report(PATH, result)

        self.assertEqual(first, second)
        self.assertEqual(len(first["dataset_sha256"]), 64)
        self.assertEqual(first["dataset_version"], 1)
        self.assertEqual(first["evaluation_mode"], "synthetic_offline")
        self.assertIsNone(first["recovery_success"])

    def test_metrics_preserved(self):
        result = evaluation()
        report = build_report(PATH, result)

        self.assertEqual(report["requested"], 5)
        self.assertEqual(report["valid_decision_rate"], 1.0)
        self.assertEqual(report["exact_match_rate"], 1.0)
        self.assertEqual(report["failure_counts"], {})

    def test_mismatched_case_id_rejected(self):
        result = evaluation()
        result["results"][0]["case_id"] = "wrong-case"

        with self.assertRaises(ValueError):
            build_report(PATH, result)

    def test_duplicate_result_id_rejected(self):
        result = evaluation()
        result["results"][1]["case_id"] = (
            result["results"][0]["case_id"]
        )

        with self.assertRaises(ValueError):
            build_report(PATH, result)

    def test_success_with_failure_reason_rejected(self):
        result = evaluation()
        result["results"][0]["failure_reason"] = "invalid_json"

        with self.assertRaises(ValueError):
            build_report(PATH, result)

    def test_failure_without_reason_rejected(self):
        result = evaluation()
        result["results"][0]["status"] = "invalid_decision"

        with self.assertRaises(ValueError):
            build_report(PATH, result)

    def test_incorrect_status_counts_rejected(self):
        result = evaluation()
        result["status_counts"]["ok"] = 0

        with self.assertRaises(ValueError):
            build_report(PATH, result)

    def test_incorrect_completed_count_rejected(self):
        result = evaluation()
        result["completed"] = 0

        with self.assertRaises(ValueError):
            build_report(PATH, result)

    def test_invalid_recovery_claim_rejected(self):
        result = evaluation()
        result["recovery_success"] = True

        with self.assertRaises(ValueError):
            build_report(PATH, result)

    def test_invalid_mode_rejected(self):
        result = evaluation()
        result["mode"] = "live_model"

        with self.assertRaises(ValueError):
            build_report(PATH, result)


if __name__ == "__main__":
    unittest.main()
