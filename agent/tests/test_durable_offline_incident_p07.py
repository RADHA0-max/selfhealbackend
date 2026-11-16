"""Durable incident evaluation and replay-prevention tests."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.durable_offline_incident import evaluate_durable_offline_incident


def signal(identifier, status):
    return {"signal_id": identifier, "target": "api", "status": status}


class FakeRPC:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def call(self, *args, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
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


class DurableIncidentTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.before = signal("incident-001", 503)
        self.after = [
            signal("after-1", 200),
            signal("after-2", 200),
            signal("after-3", 200),
        ]

    def evaluate(self, rpc, before=None, after=None):
        return evaluate_durable_offline_incident(
            rpc,
            self.before if before is None else before,
            self.after if after is None else after,
            self.directory,
        )

    def test_record_is_persisted(self):
        rpc = FakeRPC()
        record = self.evaluate(rpc)

        self.assertEqual(rpc.calls, 1)
        self.assertEqual(
            record["result"]["observation_outcome"], "SUCCESS"
        )
        self.assertFalse(record["production_recovery_verified"])

        path = (
            self.directory / "offline_incidents"
            / "run-offline-incident-incident-001.json"
        )
        self.assertTrue(path.exists())

    def test_completed_incident_cannot_replay(self):
        rpc = FakeRPC()
        self.evaluate(rpc)

        with self.assertRaises(Exception):
            self.evaluate(rpc)

        self.assertEqual(rpc.calls, 1)

    def test_failed_rpc_cannot_replay(self):
        rpc = FakeRPC(error=RuntimeError("broker unavailable"))

        with self.assertRaises(RuntimeError):
            self.evaluate(rpc)

        rpc.error = None

        with self.assertRaises(Exception):
            self.evaluate(rpc)

        self.assertEqual(rpc.calls, 1)

    def test_invalid_observations_never_call_rpc(self):
        rpc = FakeRPC()
        invalid = [
            signal("after-1", 200),
            {"signal_id": "after-2", "target": "api", "status": True},
        ]

        with self.assertRaises(ValueError):
            self.evaluate(rpc, after=invalid)

        self.assertEqual(rpc.calls, 0)

    def test_independent_incidents(self):
        rpc = FakeRPC()

        for index in range(20):
            before = signal("incident-%03d" % index, 503)
            after = [
                signal("obs-%03d-%d" % (index, step), 200)
                for step in range(3)
            ]
            record = self.evaluate(rpc, before, after)
            self.assertEqual(
                record["result"]["observation_outcome"], "SUCCESS"
            )

        self.assertEqual(rpc.calls, 20)


if __name__ == "__main__":
    unittest.main()
