"""Verify timeout outcomes remain uncertain without retries."""

import tempfile
import unittest
from pathlib import Path

from experiments.reliability_run_p06 import run_reliability_experiment


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class TimeoutTransport:
    def __init__(self):
        self.calls = 0

    def call(self, model, messages, **kwargs):
        self.calls += 1

        if self.calls == 10:
            raise TimeoutError("simulated timeout")

        return {
            "ok": True,
            "content": (
                '{"category":"unknown","target":"api",'
                '"confidence":0.5,'
                '"summary":"Insufficient evidence.",'
                '"recommended_action":"collect_more_evidence"}'
            ),
        }


class TimeoutCheckpointTests(unittest.TestCase):

    def test_timeout_is_uncertain_and_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            transport = TimeoutTransport()

            run_reliability_experiment(
                transport,
                model_id="offline-fake",
                run_id="p06-timeout-checkpoint-001",
                output_dir=directory,
                interval_seconds=2.0,
                clock=clock.monotonic,
                sleep=clock.sleep,
            )

            self.assertEqual(transport.calls, 100)

            checkpoint_files = list(
                Path(directory).rglob("run-*-outcome.json")
            )

            self.assertEqual(len(checkpoint_files), 100)

            import json

            uncertain = [
                json.loads(path.read_text())
                for path in checkpoint_files
                if json.loads(path.read_text())["status"] == "uncertain"
            ]

            self.assertEqual(len(uncertain), 1)


if __name__ == "__main__":
    unittest.main()
