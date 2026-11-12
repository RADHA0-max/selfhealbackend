import json
import tempfile
import unittest
from pathlib import Path

from experiments.response_capture import (
    CaptureValidationError,
    load_capture,
    validate_capture,
)


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


def valid_capture():
    return {
        "schema_version": 1,
        "capture_source": "model_inference",
        "model_id": "test-model",
        "run_id": "run-001",
        "captured_at": "2026-11-12T10:00:00Z",
        "responses": {"case-001": '{"category":"unknown"}'},
    }


class ResponseCaptureTests(unittest.TestCase):
    def test_valid_capture(self):
        responses = validate_capture(valid_capture(), DATASET)
        self.assertEqual(
            responses,
            {"case-001": '{"category":"unknown"}'},
        )

    def test_missing_response_rejected(self):
        capture = valid_capture()
        capture["responses"] = {}

        with self.assertRaises(CaptureValidationError):
            validate_capture(capture, DATASET)

    def test_extra_response_rejected(self):
        capture = valid_capture()
        capture["responses"]["other"] = "{}"

        with self.assertRaises(CaptureValidationError):
            validate_capture(capture, DATASET)

    def test_invalid_metadata_rejected(self):
        for field, value in (
            ("schema_version", True),
            ("capture_source", "synthetic_offline"),
            ("model_id", "../unsafe"),
            ("run_id", ""),
            ("captured_at", "not-a-date"),
            ("captured_at", "2026-11-12T10:00:00"),
        ):
            with self.subTest(field=field, value=value):
                capture = valid_capture()
                capture[field] = value

                with self.assertRaises(CaptureValidationError):
                    validate_capture(capture, DATASET)

    def test_oversized_response_rejected(self):
        capture = valid_capture()
        capture["responses"]["case-001"] = "x" * 16385

        with self.assertRaises(CaptureValidationError):
            validate_capture(capture, DATASET)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.json"
            path.write_text(
                '{"schema_version":1,"schema_version":1}',
                encoding="utf-8",
            )

            with self.assertRaises(CaptureValidationError):
                load_capture(path, DATASET)

    def test_capture_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.json"
            path.write_text(
                json.dumps(valid_capture()),
                encoding="utf-8",
            )

            self.assertEqual(
                load_capture(path, DATASET),
                valid_capture()["responses"],
            )


if __name__ == "__main__":
    unittest.main()
