"""End-to-end offline reliability recording and reporting test."""

import json
import tempfile
import unittest

from experiments.reliability_report_p06 import summarize_record_file
from experiments.reliability_run_p06 import run_reliability_experiment


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
            "ok": True,
            "content": json.dumps({
                "category": "unknown",
                "target": "api",
                "confidence": 0.5,
                "summary": "Insufficient evidence.",
                "recommended_action": "collect_more_evidence",
            }),
        }


class ReliabilityReportingIntegrationTests(unittest.TestCase):

    def test_complete_run_produces_consistent_report(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            transport = FakeTransport()

            path = run_reliability_experiment(
                transport,
                model_id="offline-fake",
                run_id="p06-report-integration-001",
                output_dir=directory,
                interval_seconds=2.0,
                clock=clock.monotonic,
                sleep=clock.sleep,
            )

            report = summarize_record_file(path)

            self.assertEqual(transport.calls, 100)
            self.assertEqual(report["requested"], 100)
            self.assertEqual(report["captured_responses"], 100)
            self.assertEqual(report["missing_responses"], 0)
            self.assertEqual(report["schema_valid_diagnoses"], 100)
            self.assertEqual(
                report["schema_validity_rate_all_requests"], 1.0
            )
            self.assertFalse(report["inference_verified"])
            self.assertIsNone(report["recovery_success"])


if __name__ == "__main__":
    unittest.main()
