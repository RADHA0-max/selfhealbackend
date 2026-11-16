"""Evidence-integrity regression tests for P09."""

import copy
import tempfile
import unittest

from chaos.measured_http_experiment_p09 import (
    MeasurementError,
    write_measured_report,
)
from chaos.recovery_timeline import evaluate_timeline


def valid_report():
    events = [
        {"time_ms": 0, "target": "api", "status": 503, "latency_ms": 10},
        {"time_ms": 100, "target": "api", "status": 200, "latency_ms": 10},
        {"time_ms": 200, "target": "api", "status": 200, "latency_ms": 10},
        {"time_ms": 300, "target": "api", "status": 200, "latency_ms": 10},
    ]

    return {
        "report_version": 1,
        "experiment_id": "p09-integrity",
        "evidence_source": "measured_loopback_http",
        "endpoint": "http://127.0.0.1:18080/ready",
        "events": events,
        "healthy_latency_ms": 1000,
        "timeline": evaluate_timeline(events),
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "envoy_verified": False,
        "production_recovery_verified": False,
    }


class EvidenceIntegrityTests(unittest.TestCase):

    def test_valid_report(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(
                write_measured_report(directory, valid_report()).exists()
            )

    def test_tampered_timeline_rejected(self):
        report = valid_report()
        report["timeline"]["observation_outcome"] = "FAILED"

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(directory, report)

    def test_tampered_status_rejected(self):
        report = valid_report()
        report["events"][0]["status"] = 200

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(directory, report)

    def test_extra_claim_rejected(self):
        report = valid_report()
        report["agent_recovered_production"] = True

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(directory, report)

    def test_invalid_timeline_rejected(self):
        report = valid_report()
        report["events"][1]["time_ms"] = 0

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MeasurementError):
                write_measured_report(directory, report)

    def test_invalid_endpoint_rejected(self):
        report = valid_report()
        report["endpoint"] = "http://example.com/ready"

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                write_measured_report(directory, report)


if __name__ == "__main__":
    unittest.main()
