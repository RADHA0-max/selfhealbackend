"""Ensure persisted measurements retain their evaluation threshold."""

import tempfile
import unittest

from chaos.measured_http_experiment_p09 import (
    MeasurementError,
    write_measured_report,
)
from chaos.test_evidence_integrity_p09 import valid_report
from chaos.recovery_timeline import evaluate_timeline


class ThresholdIntegrityTests(unittest.TestCase):

    def test_custom_threshold_is_preserved(self):
        report = valid_report()
        report["healthy_latency_ms"] = 5
        report["timeline"] = evaluate_timeline(
            report["events"],
            healthy_latency_ms=5,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = write_measured_report(directory, report)
            self.assertTrue(path.exists())

    def test_tampered_threshold_rejected(self):
        report = valid_report()
        report["healthy_latency_ms"] = 5

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(directory, report)

    def test_invalid_threshold_rejected(self):
        report = valid_report()
        report["healthy_latency_ms"] = True

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(directory, report)


if __name__ == "__main__":
    unittest.main()
