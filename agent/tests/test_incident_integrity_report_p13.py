"""P13 combined integrity report tests."""

import tempfile
import unittest
from pathlib import Path

from agent.incident_integrity_report_p13 import report_incident_integrity
from agent.incident_reconciliation_p13 import IncidentReconciliationError
from agent.measured_audit_p12 import MeasuredAuditError
from agent.measured_receipt_p11 import evaluate_measured_receipt
from agent.tests.test_measured_incident_p10 import FakeRPC, report_for
from chaos.envoy_observer_p09 import write_observation
from experiments.run_record import write_run_record


class IntegrityReportTests(unittest.TestCase):

    def _measured(self, root):
        evidence = Path(root) / "evidence"
        evidence.mkdir()
        report_path = write_observation(
            evidence,
            report_for([503, 503, 503, 200, 200, 200]),
        )
        output = Path(root) / "records"
        evaluate_measured_receipt(FakeRPC(), report_path, output)
        return output, evidence

    def test_empty(self):
        with tempfile.TemporaryDirectory() as root:
            report = report_incident_integrity(root)
            self.assertEqual(report["incidents"]["attempted"], 0)
            self.assertEqual(report["measured_receipts"]["receipts_verified"], 0)
            self.assertFalse(report["requires_manual_review"])

    def test_measured_incident_and_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            output, evidence = self._measured(root)
            report = report_incident_integrity(
                output, evidence_dir=evidence
            )
            self.assertEqual(report["incidents"]["completed"], 1)
            self.assertEqual(report["measured_receipts"]["receipts_verified"], 1)
            self.assertEqual(
                report["measured_receipts"]["evidence_files_verified"], 1
            )
            self.assertFalse(report["production_recovery_verified"])

    def test_unresolved_intent_requires_review(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()

            write_run_record(
                directory,
                "offline-incident-demo-intent",
                {
                    "record_version": 1,
                    "record_type": "offline_incident_intent",
                    "run_id": "offline-incident-demo",
                    "status": "uncertain",
                    "automatic_replay_allowed": False,
                },
            )

            report = report_incident_integrity(root)
            self.assertEqual(report["incidents"]["unresolved"], 1)
            self.assertTrue(report["requires_manual_review"])
            self.assertFalse(report["automatic_replay_allowed"])

    def test_corrupt_incident_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "offline_incidents"
            directory.mkdir()
            (directory / "run-offline-incident-demo.json").write_text(
                '{"record_type":"offline_incident_observation"}'
            )
            with self.assertRaises(IncidentReconciliationError):
                report_incident_integrity(root)

    def test_missing_measured_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            output, _ = self._measured(root)
            receipt_dir = output / "measured_receipts"
            for path in receipt_dir.iterdir():
                path.unlink()

            # P12's orphan detection only runs when its directory exists.
            # The combined report must not silently certify this as complete.
            with self.assertRaises(MeasuredAuditError):
                report_incident_integrity(output)

    def test_no_recovery_claims(self):
        with tempfile.TemporaryDirectory() as root:
            report = report_incident_integrity(root)
            self.assertFalse(report["mitigation_executed"])
            self.assertFalse(report["recovery_attributed_to_agent"])
            self.assertFalse(report["production_recovery_verified"])


if __name__ == "__main__":
    unittest.main()
