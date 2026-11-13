"""Offline integration tests for the P06 reliability experiment."""

import json
import tempfile
import unittest
from pathlib import Path

from experiments.reliability_run_p06 import run_reliability_experiment


VALID_DIAGNOSIS = json.dumps({
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


class FakeTransport:
    def __init__(self):
        self.calls = 0

    def call(self, model, messages, **kwargs):
        self.calls += 1
        return {
            "request_id": "offline",
            "ok": True,
            "content": VALID_DIAGNOSIS,
            "embedding": None,
            "error": None,
        }


class ReliabilityRunTests(unittest.TestCase):

    def test_records_100_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            transport = FakeTransport()

            record_path = run_reliability_experiment(
                transport,
                model_id="offline-fake",
                run_id="p06-offline-001",
                output_dir=directory,
                interval_seconds=2.0,
                clock=clock.monotonic,
                sleep=clock.sleep,
            )

            record = json.loads(Path(record_path).read_text())

            self.assertEqual(transport.calls, 100)
            self.assertEqual(record["requested"], 100)
            self.assertEqual(record["completed"], 100)
            self.assertEqual(len(record["partial_responses"]), 100)
            self.assertEqual(clock.now, 198.0)
            self.assertFalse(record["inference_verified"])
            self.assertIsNone(record["recovery_success"])

    def test_rejects_duplicate_run_without_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            transport = FakeTransport()

            kwargs = {
                "model_id": "offline-fake",
                "run_id": "p06-offline-002",
                "output_dir": directory,
                "interval_seconds": 2.0,
                "clock": clock.monotonic,
                "sleep": clock.sleep,
            }

            run_reliability_experiment(transport, **kwargs)
            self.assertEqual(transport.calls, 100)

            with self.assertRaises(ValueError):
                run_reliability_experiment(transport, **kwargs)

            self.assertEqual(transport.calls, 100)


if __name__ == "__main__":
    unittest.main()
