import json
import tempfile
import unittest
from pathlib import Path

from experiments.capture_evaluation import evaluate_capture
from experiments.response_capture import CaptureValidationError


DATASET = {
    "schema_version": 1,
    "dataset_type": "synthetic",
    "cases": [
        {
            "case_id": "case-001",
            "signal": {
                "signal_id": "case-001",
                "target": "api",
                "status": 503,
            },
            "expected": {
                "category": "service_failure",
                "target": "api",
                "recommended_action": "investigate_api",
            },
        }
    ],
}

VALID_DIAGNOSIS = {
    "category": "service_failure",
    "target": "api",
    "confidence": 0.95,
    "summary": "Synthetic API failure",
    "recommended_action": "investigate_api",
}


class CaptureEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.dataset_path = root / "dataset.json"
        self.capture_path = root / "capture.json"

        self.dataset_path.write_text(
            json.dumps(DATASET), encoding="utf-8"
        )

        self.capture = {
            "schema_version": 1,
            "capture_source": "model_inference",
            "model_id": "test-model",
            "run_id": "run-001",
            "captured_at": "2026-11-12T10:00:00Z",
            "responses": {
                "case-001": json.dumps(VALID_DIAGNOSIS),
            },
        }
        self.write_capture()

    def write_capture(self):
        self.capture_path.write_text(
            json.dumps(self.capture), encoding="utf-8"
        )

    def test_valid_capture_scored(self):
        report = evaluate_capture(
            self.dataset_path, self.capture_path
        )

        self.assertEqual(report["requested"], 1)
        self.assertEqual(report["completed"], 1)
        self.assertEqual(report["valid_decision_rate"], 1.0)
        self.assertEqual(report["exact_match_rate"], 1.0)
        self.assertEqual(
            report["evaluation_mode"],
            "external_capture_offline",
        )
        self.assertFalse(report["inference_verified"])
        self.assertIsNone(report["recovery_success"])

    def test_invalid_diagnosis_counted(self):
        self.capture["responses"]["case-001"] = "not json"
        self.write_capture()

        report = evaluate_capture(
            self.dataset_path, self.capture_path
        )

        self.assertEqual(report["completed"], 0)
        self.assertEqual(report["valid_decision_rate"], 0.0)
        self.assertEqual(report["exact_match_rate"], 0.0)

    def test_missing_response_rejected(self):
        self.capture["responses"] = {}
        self.write_capture()

        with self.assertRaises(CaptureValidationError):
            evaluate_capture(
                self.dataset_path, self.capture_path
            )

    def test_fingerprints_present(self):
        report = evaluate_capture(
            self.dataset_path, self.capture_path
        )

        self.assertEqual(len(report["dataset_sha256"]), 64)
        self.assertEqual(len(report["capture_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
