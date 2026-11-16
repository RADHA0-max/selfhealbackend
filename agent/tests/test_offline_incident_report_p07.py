"""Offline incident report integration tests."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.durable_offline_incident import evaluate_durable_offline_incident
from agent.offline_incident_report import (
    IncidentReportError,
    summarize_offline_incidents,
)


def signal(identifier, status):
    return {"signal_id": identifier, "target": "api", "status": status}


class FakeRPC:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def call(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("offline injected failure")
        return {
            "ok": True,
            "content": json.dumps({
                "category": "service_failure",
                "target": "api",
                "confidence": 0.8,
                "summary": "Synthetic offline diagnosis.",
                "recommended_action": "investigate_api",
            }),
        }


class OfflineIncidentReportTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def run_incident(self, identifier, statuses, rpc=None):
        rpc = rpc or FakeRPC()
        before = signal(identifier, 503)
        observations = [
            signal("%s-after-%d" % (identifier, index), status)
            for index, status in enumerate(statuses)
        ]
        return evaluate_durable_offline_incident(
            rpc, before, observations, self.directory
        )

    def test_empty_report(self):
        report = summarize_offline_incidents(self.directory)
        self.assertEqual(report["attempted"], 0)

    def test_mixed_incident_outcomes(self):
        self.run_incident("success", [200, 200, 200])
        self.run_incident("failure", [200, 503, 200])
        self.run_incident("inconclusive", [200])

        report = summarize_offline_incidents(self.directory)

        self.assertEqual(report["attempted"], 3)
        self.assertEqual(report["completed"], 3)
        self.assertEqual(report["observed_success"], 1)
        self.assertEqual(report["observed_failure"], 1)
        self.assertEqual(report["inconclusive"], 1)
        self.assertFalse(report["production_recovery_verified"])

    def test_failed_rpc_is_unresolved(self):
        with self.assertRaises(RuntimeError):
            self.run_incident(
                "failed-rpc", [200, 200, 200], FakeRPC(fail=True)
            )

        report = summarize_offline_incidents(self.directory)

        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["completed"], 0)
        self.assertEqual(report["unresolved"], 1)

    def test_invalid_record_rejected(self):
        directory = self.directory / "offline_incidents"
        directory.mkdir()

        path = directory / "run-offline-incident-invalid.json"
        path.write_text("{invalid", encoding="utf-8")

        with self.assertRaises(IncidentReportError):
            summarize_offline_incidents(self.directory)


if __name__ == "__main__":
    unittest.main()
