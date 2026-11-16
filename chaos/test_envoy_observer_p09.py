"""Offline security and evidence tests for the isolated Envoy observer."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chaos.envoy_observer_p09 import (
    ENVOY_URL,
    ObserverError,
    observe_envoy,
    write_observation,
)
from chaos.recovery_timeline import evaluate_timeline


def sample_report():
    events = [
        {"time_ms": 0, "target": "api", "status": 503, "latency_ms": 10},
        {"time_ms": 100, "target": "api", "status": 503, "latency_ms": 10},
        {"time_ms": 200, "target": "api", "status": 200, "latency_ms": 10},
        {"time_ms": 300, "target": "api", "status": 200, "latency_ms": 10},
        {"time_ms": 400, "target": "api", "status": 200, "latency_ms": 10},
    ]

    return {
        "report_version": 1,
        "experiment_id": "p09-observer-test",
        "evidence_source": "isolated_envoy_http",
        "endpoint": ENVOY_URL,
        "events": events,
        "healthy_latency_ms": 1000,
        "timeline": evaluate_timeline(events),
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }


class ObserverTests(unittest.TestCase):

    def test_valid_report_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_observation(directory, sample_report())
            self.assertTrue(path.is_file())

    def test_report_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            write_observation(directory, sample_report())

            with self.assertRaises(FileExistsError):
                write_observation(directory, sample_report())

    def test_tampered_timeline_rejected(self):
        report = sample_report()
        report["timeline"]["observation_outcome"] = "FAILED"

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ObserverError):
                write_observation(directory, report)

    def test_tampered_events_rejected(self):
        report = sample_report()
        report["events"][0]["status"] = 200

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ObserverError):
                write_observation(directory, report)

    def test_production_claim_rejected(self):
        report = sample_report()
        report["production_recovery_verified"] = True

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ObserverError):
                write_observation(directory, report)

    def test_wrong_endpoint_rejected(self):
        report = sample_report()
        report["endpoint"] = "http://example.com/ready"

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ObserverError):
                write_observation(directory, report)

    def test_invalid_request_count_rejected_before_network(self):
        with patch(
            "chaos.envoy_observer_p09.build_opener",
            side_effect=AssertionError("network setup must not run"),
        ):
            with self.assertRaises(ObserverError):
                observe_envoy(experiment_id="test", count=100)

    def test_invalid_experiment_id_rejected_before_network(self):
        with patch(
            "chaos.envoy_observer_p09.build_opener",
            side_effect=AssertionError("network setup must not run"),
        ):
            with self.assertRaises(ObserverError):
                observe_envoy(experiment_id="../escape")

    def test_invalid_latency_threshold_rejected(self):
        with self.assertRaises(ObserverError):
            observe_envoy(
                experiment_id="test",
                healthy_latency_ms=True,
            )

    def test_extra_report_fields_rejected(self):
        report = sample_report()
        report["agent_mitigated"] = True

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ObserverError):
                write_observation(directory, report)


if __name__ == "__main__":
    unittest.main()
