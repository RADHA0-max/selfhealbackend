import json
import unittest

from experiments.live_diagnosis_runner import (
    CaptureRunError,
    capture_diagnoses,
)


def dataset():
    return {
        "schema_version": 1,
        "dataset_type": "synthetic",
        "cases": [{
            "case_id": "p05-test-001",
            "signal": {
                "signal_id": "p05-test-001",
                "target": "api",
                "status": 503,
            },
            "expected": {
                "category": "service_failure",
                "target": "api",
                "recommended_action": "investigate_api",
            },
        }],
    }


VALID = json.dumps({
    "category": "service_failure",
    "target": "api",
    "confidence": 0.9,
    "summary": "API unavailable",
    "recommended_action": "investigate_api",
})


class FakeTransport:
    def __init__(self, content=VALID, error=None):
        self.content = content
        self.error = error
        self.calls = 0

    def call(self, model, messages, *, max_tokens, temperature):
        self.calls += 1
        if self.error:
            raise self.error
        return {"ok": True, "content": self.content}


class CaptureRunnerTests(unittest.TestCase):
    def test_valid_capture(self):
        rpc = FakeTransport()
        result = capture_diagnoses(
            dataset(), rpc, model_id="fast", run_id="p05-test"
        )
        self.assertEqual(rpc.calls, 1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["failures"], {})
        self.assertEqual(
            result["capture"]["responses"]["p05-test-001"], VALID
        )

    def test_invalid_json_is_retained(self):
        result = capture_diagnoses(
            dataset(),
            FakeTransport(content="{invalid"),
            model_id="fast",
            run_id="p05-test",
        )
        self.assertEqual(result["completed"], 1)
        self.assertIn("p05-test-001", result["failures"])
        self.assertEqual(
            result["capture"]["responses"]["p05-test-001"],
            "{invalid",
        )

    def test_transport_failure_is_not_fake_json(self):
        result = capture_diagnoses(
            dataset(),
            FakeTransport(error=TimeoutError("timeout")),
            model_id="fast",
            run_id="p05-test",
        )
        self.assertEqual(result["completed"], 0)
        self.assertIsNone(result["capture"])
        self.assertEqual(
            result["failures"]["p05-test-001"],
            "TimeoutError",
        )

    def test_invalid_metadata_never_calls_transport(self):
        rpc = FakeTransport()
        with self.assertRaises(ValueError):
            capture_diagnoses(
                dataset(), rpc, model_id="invalid model!", run_id="test"
            )
        self.assertEqual(rpc.calls, 0)


    def test_oversized_response(self):
        rpc = FakeTransport(content="x" * 16385)

        result = capture_diagnoses(
            dataset(), rpc, model_id="fast", run_id="p05-test"
        )

        self.assertEqual(rpc.calls, 1)
        self.assertEqual(result["completed"], 0)
        self.assertIsNone(result["capture"])
        self.assertEqual(result["partial_responses"], {})
        self.assertEqual(
            result["failures"]["p05-test-001"],
            "response_too_large",
        )

    def test_broker_error_is_not_model_content(self):
        class FailedBroker:
            def call(self, model, messages, *, max_tokens, temperature):
                return {
                    "ok": False,
                    "content": "{invalid",
                    "error": "broker_failure",
                }

        result = capture_diagnoses(
            dataset(), FailedBroker(),
            model_id="fast", run_id="p05-test",
        )

        self.assertEqual(result["completed"], 0)
        self.assertIsNone(result["capture"])
        self.assertEqual(result["partial_responses"], {})
        self.assertIn("p05-test-001", result["failures"])

    def test_partial_capture_preserves_success(self):
        data = dataset()
        second = json.loads(json.dumps(data["cases"][0]))
        second["case_id"] = "p05-test-002"
        second["signal"]["signal_id"] = "p05-test-002"
        data["cases"].append(second)

        class PartialTransport:
            def __init__(self):
                self.calls = 0

            def call(self, model, messages, *, max_tokens, temperature):
                self.calls += 1

                if self.calls == 2:
                    raise TimeoutError("timeout")

                return {"ok": True, "content": VALID}

        rpc = PartialTransport()

        result = capture_diagnoses(
            data, rpc, model_id="fast", run_id="p05-test"
        )

        self.assertEqual(rpc.calls, 2)
        self.assertEqual(result["requested"], 2)
        self.assertEqual(result["completed"], 1)
        self.assertIsNone(result["capture"])
        self.assertEqual(
            result["partial_responses"]["p05-test-001"],
            VALID,
        )
        self.assertEqual(
            result["failures"]["p05-test-002"],
            "TimeoutError",
        )


if __name__ == "__main__":
    unittest.main()
