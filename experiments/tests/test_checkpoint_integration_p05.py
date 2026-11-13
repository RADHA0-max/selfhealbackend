import json
import tempfile
import unittest
from pathlib import Path

from experiments.recorded_diagnosis_run import run_and_record
from experiments.run_checkpoint import (
    inspect_checkpoints,
    write_case_checkpoint,
)
from experiments.run_record import RunRecordError
from experiments.live_diagnosis_runner import CaptureRunError


def dataset(case_id="case1"):
    return {
        "schema_version": 1,
        "dataset_type": "synthetic",
        "cases": [{
            "case_id": case_id,
            "signal": {
                "signal_id": case_id,
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


class Transport:
    def __init__(self, before_call=None, fail=False):
        self.calls = 0
        self.before_call = before_call
        self.fail = fail

    def call(self, model, messages, **kwargs):
        self.calls += 1
        if self.before_call:
            self.before_call()
        if self.fail:
            raise TimeoutError("simulated timeout")
        return {
            "ok": True,
            "content": (
                '{"category":"service_failure","target":"api",'
                '"confidence":0.9,"summary":"unavailable",'
                '"recommended_action":"none"}'
            ),
        }


class CheckpointIntegrationTests(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)

    def run_capture(self, transport, case_id="case1"):
        return run_and_record(
            dataset(case_id),
            transport,
            model_id="offline-test",
            run_id="run1",
            output_dir=self.directory,
        )

    def test_intent_exists_before_transport(self):
        def verify():
            checkpoints = inspect_checkpoints(
                self.directory, "run1"
            )
            self.assertEqual(
                checkpoints["case1"]["status"], "uncertain"
            )
            self.assertNotIn("case1-outcome", checkpoints)

        transport = Transport(before_call=verify)
        self.run_capture(transport)
        self.assertEqual(transport.calls, 1)

    def test_success_persists_outcome(self):
        self.run_capture(Transport())
        checkpoints = inspect_checkpoints(
            self.directory, "run1"
        )
        self.assertEqual(
            checkpoints["case1-outcome"]["status"],
            "completed",
        )
        self.assertIn(
            '"category":"service_failure"',
            checkpoints["case1-outcome"]["response"],
        )

    def test_failure_persists_outcome(self):
        self.run_capture(Transport(fail=True))
        checkpoints = inspect_checkpoints(
            self.directory, "run1"
        )
        self.assertEqual(
            checkpoints["case1-outcome"]["status"],
            "failed",
        )
        self.assertEqual(
            checkpoints["case1-outcome"]["error"],
            "TimeoutError",
        )

    def test_interrupted_run_cannot_replay(self):
        write_case_checkpoint(
            self.directory, "run1", "case1",
            status="uncertain",
        )
        transport = Transport()

        with self.assertRaises(RunRecordError):
            self.run_capture(transport)

        self.assertEqual(transport.calls, 0)

    def test_failed_run_evaluation_counts_missing_response(self):
        path = self.run_capture(Transport(fail=True))
        record = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(record["requested"], 1)
        self.assertEqual(record["completed"], 0)
        self.assertEqual(record["partial_responses"], {})
        self.assertIsNone(record["capture"])

        evaluation = record["evaluation"]
        self.assertEqual(evaluation["requested"], 1)
        self.assertEqual(evaluation["valid_decision_rate"], 0.0)
        self.assertEqual(
            record["evaluation_mode"],
            "recorded_capture_offline",
        )
        self.assertIs(record["inference_verified"], False)
        self.assertIsNone(record["recovery_success"])

    def test_long_case_id_rejected_before_transport(self):
        transport = Transport()

        with self.assertRaises(CaptureRunError):
            self.run_capture(transport, case_id="a" * 64)

        self.assertEqual(transport.calls, 0)

    def test_reserved_suffix_rejected_before_transport(self):
        transport = Transport()

        with self.assertRaises(CaptureRunError):
            self.run_capture(transport, case_id="case1-outcome")

        self.assertEqual(transport.calls, 0)


if __name__ == "__main__":
    unittest.main()
