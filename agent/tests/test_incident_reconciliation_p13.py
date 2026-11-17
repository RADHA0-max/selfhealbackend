"""P13 durable incident reconciliation tests."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.incident_reconciliation_p13 import (
    IncidentReconciliationError,
    reconcile_offline_incidents,
)
from experiments.run_record import write_run_record


class ReconciliationTests(unittest.TestCase):

    def _intent(self, directory, incident="demo"):
        return write_run_record(
            directory,
            "offline-incident-" + incident + "-intent",
            {
                "record_version": 1,
                "record_type": "offline_incident_intent",
                "run_id": "offline-incident-" + incident,
                "status": "uncertain",
                "automatic_replay_allowed": False,
            },
        )

    def _observation(self, directory, incident="demo", outcome="FAILED"):
        return write_run_record(
            directory,
            "offline-incident-" + incident,
            {
                "record_version": 1,
                "record_type": "offline_incident_observation",
                "run_id": "offline-incident-" + incident,
                "result": {
                    "observation_outcome": outcome,
                    "mitigation_executed": False,
                    "recovery_attributed_to_agent": False,
                },
                "production_recovery_verified": False,
            },
        )

    def test_empty(self):
        with tempfile.TemporaryDirectory() as root:
            result = reconcile_offline_incidents(root)
            self.assertEqual(result["attempted"], 0)
            self.assertFalse(result["automatic_replay_allowed"])

    def test_intent_only_is_unresolved(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            self._intent(directory)

            result = reconcile_offline_incidents(root)
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["unresolved"], 1)
            self.assertEqual(result["completed"], 0)

    def test_completed_observation(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            self._intent(directory)
            self._observation(directory)

            result = reconcile_offline_incidents(root)
            self.assertEqual(result["completed"], 1)
            self.assertEqual(result["observed_failure"], 1)

    def test_mixed_completed_and_unresolved(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            self._intent(directory, "one")
            self._observation(directory, "one", "SUCCESS")
            self._intent(directory, "two")

            result = reconcile_offline_incidents(root)
            self.assertEqual(result["attempted"], 2)
            self.assertEqual(result["completed"], 1)
            self.assertEqual(result["unresolved"], 1)
            self.assertEqual(result["observed_success"], 1)

    def test_observation_without_intent_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            self._observation(directory)

            with self.assertRaises(IncidentReconciliationError):
                reconcile_offline_incidents(root)

    def test_tampered_intent_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            path = self._intent(directory)

            record = json.loads(path.read_text())
            record["automatic_replay_allowed"] = True
            path.write_text(json.dumps(record))

            with self.assertRaises(IncidentReconciliationError):
                reconcile_offline_incidents(root)

    def test_symlinked_record_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            path = self._intent(directory)
            other = directory / "original"
            path.rename(other)
            path.symlink_to(other)

            with self.assertRaises(IncidentReconciliationError):
                reconcile_offline_incidents(root)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            path = self._intent(directory)
            path.write_text('{"run_id":"x","run_id":"x"}')

            with self.assertRaises(IncidentReconciliationError):
                reconcile_offline_incidents(root)

    def test_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            intent = self._intent(directory)
            observation = self._observation(directory)

            before = {
                intent: intent.read_bytes(),
                observation: observation.read_bytes(),
            }

            reconcile_offline_incidents(root)

            self.assertEqual(
                before,
                {path: path.read_bytes() for path in before},
            )


if __name__ == "__main__":
    unittest.main()
