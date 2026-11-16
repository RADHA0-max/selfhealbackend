"""Offline failure-path tests for the P06 reliability experiment."""

import json
import tempfile
import unittest
from pathlib import Path

from experiments.reliability_run_p06 import run_reliability_experiment


VALID_RESPONSE = json.dumps({
    "category": "unknown",
    "target": "api",
    "confidence": 0.5,
    "summary": "Insufficient evidence.",
    "recommended_action": "collect_more_evidence",
})


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FailingTransport:
    def __init__(self):
        self.calls = 0

    def call(self, model, messages, **kwargs):
        self.calls += 1

        if self.calls == 10:
            raise TimeoutError("simulated timeout")

        if self.calls == 20:
            return {
                "ok": False,
                "content": None,
                "error": "simulated broker failure",
            }

        return {
            "ok": True,
            "content": VALID_RESPONSE,
        }


class ReliabilityFailureTests(unittest.TestCase):

    def test_failures_are_recorded_without_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            transport = FailingTransport()

            path = run_reliability_experiment(
                transport,
                model_id="offline-fake",
                run_id="p06-failure-001",
                output_dir=directory,
                interval_seconds=2.0,
                clock=clock.monotonic,
                sleep=clock.sleep,
            )

            record = json.loads(Path(path).read_text())

            self.assertEqual(transport.calls, 100)
            self.assertEqual(record["requested"], 100)
            self.assertEqual(record["completed"], 98)
            self.assertEqual(len(record["failures"]), 2)
            self.assertEqual(len(record["partial_responses"]), 98)
            self.assertIsNone(record["capture"])
            self.assertFalse(record["inference_verified"])
            self.assertIsNone(record["recovery_success"])

            self.assertEqual(
                len(list(Path(directory).glob("run-*.json"))),
                1,
            )


if __name__ == "__main__":
    unittest.main()
