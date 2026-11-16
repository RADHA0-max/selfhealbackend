"""Real loopback HTTP measurements through the P09 evidence pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

from chaos.measured_http_experiment_p09 import (
    MeasurementError,
    evaluate_measured_http,
    write_measured_report,
)
from testbed.app.test_real_http_p09 import local_testbed


class MeasuredHTTPExperimentTests(unittest.TestCase):

    def measure(self, mode, **kwargs):
        with local_testbed(mode) as port:
            return evaluate_measured_http(
                f"http://127.0.0.1:{port}/ready",
                experiment_id=f"p09-{mode}",
                count=9,
                interval_seconds=0.1,
                **kwargs,
            )

    def test_recovery_measured_over_http(self):
        report = self.measure("recovering")
        self.assertEqual(
            [event["status"] for event in report["events"]],
            [503, 503, 503, 200, 200, 200, 200, 200, 200],
        )
        self.assertEqual(
            report["timeline"]["observation_outcome"],
            "SUCCESS",
        )
        self.assertFalse(report["recovery_attributed_to_agent"])

    def test_regression_measured_over_http(self):
        report = self.measure("regression")
        self.assertEqual(
            report["timeline"]["observation_outcome"],
            "FAILED",
        )
        self.assertGreaterEqual(
            report["timeline"]["regression_count"],
            1,
        )

    def test_outage_measured_over_http(self):
        report = self.measure("outage")
        self.assertEqual(
            report["timeline"]["observation_outcome"],
            "FAILED",
        )

    def test_latency_measured_over_http(self):
        report = self.measure(
            "latency",
            healthy_latency_ms=100,
        )
        self.assertTrue(
            all(event["latency_ms"] >= 200 for event in report["events"])
        )
        self.assertEqual(
            report["timeline"]["observation_outcome"],
            "FAILED",
        )

    def test_healthy_negative_control(self):
        report = self.measure("healthy")
        self.assertEqual(
            report["timeline"]["observation_outcome"],
            "INCONCLUSIVE",
        )

    def test_evidence_provenance(self):
        report = self.measure("recovering")
        self.assertEqual(
            report["evidence_source"],
            "measured_loopback_http",
        )
        self.assertFalse(report["envoy_verified"])
        self.assertFalse(report["production_recovery_verified"])
        self.assertFalse(report["mitigation_executed"])

    def test_immutable_report(self):
        report = self.measure("recovering")

        with tempfile.TemporaryDirectory() as directory:
            path = write_measured_report(directory, report)
            self.assertEqual(
                json.loads(path.read_text()),
                report,
            )

            with self.assertRaises(FileExistsError):
                write_measured_report(directory, report)

    def test_invalid_report_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(
                    directory,
                    {
                        "experiment_id": "../escape",
                        "evidence_source": "measured_loopback_http",
                    },
                )

            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_no_false_production_claim(self):
        report = self.measure("recovering")
        report["production_recovery_verified"] = True

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(directory, report)


if __name__ == "__main__":
    unittest.main()
