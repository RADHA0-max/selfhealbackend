"""P12 offline receipt auditor: valid records and adversarial cases."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.measured_audit_p12 import (
    MeasuredAuditError,
    audit_measured_receipts,
)
from agent.measured_receipt_p11 import evaluate_measured_receipt
from agent.tests.test_measured_incident_p10 import FakeRPC, report_for
from chaos.envoy_observer_p09 import write_observation


class MeasuredAuditTests(unittest.TestCase):

    def _records(self, directory, statuses=(503, 503, 503, 200, 200, 200)):
        root = Path(directory)
        evidence = root / "evidence"
        evidence.mkdir()

        path = write_observation(
            evidence,
            report_for(list(statuses)),
        )

        output = root / "records"
        evaluate_measured_receipt(FakeRPC(), path, output)

        receipt = (
            output
            / "measured_receipts"
            / "run-measured-receipt-p10-integration.json"
        )
        incident = (
            output
            / "offline_incidents"
            / "run-offline-incident-p10-integration-0.json"
        )
        intent = (
            output
            / "offline_incidents"
            / "run-offline-incident-p10-integration-0-intent.json"
        )

        return output, receipt, incident, intent

    def test_empty_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = audit_measured_receipts(directory)
            self.assertEqual(summary["receipts_verified"], 0)
            self.assertFalse(summary["production_recovery_verified"])

    def test_realistic_recovery_and_conservative_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, _, _ = self._records(directory)
            summary = audit_measured_receipts(output)

            self.assertEqual(summary["receipts_verified"], 1)
            self.assertEqual(summary["observed_success"], 1)
            self.assertEqual(summary["uninterrupted_failure"], 1)
            self.assertFalse(summary["observer_authenticated"])
            self.assertFalse(summary["production_recovery_verified"])

    def test_missing_incident_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, incident, _ = self._records(directory)
            incident.unlink()

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_missing_intent_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, _, intent = self._records(directory)
            intent.unlink()

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_modified_incident_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, incident, _ = self._records(directory)
            record = json.loads(incident.read_text())
            record["result"]["observation_outcome"] = "SUCCESS"
            incident.write_text(json.dumps(record))

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_modified_receipt_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, receipt, _, _ = self._records(directory)
            record = json.loads(receipt.read_text())
            record["incident_sha256"] = "0" * 64
            receipt.write_text(json.dumps(record))

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, receipt, _, _ = self._records(directory)
            receipt.write_text('{"receipt_version":1,"receipt_version":1}')

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_symlinked_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, receipt, _, _ = self._records(directory)
            original = receipt.with_suffix(".backup")
            receipt.rename(original)
            receipt.symlink_to(original)

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_unsupported_production_claim_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, receipt, _, _ = self._records(directory)
            record = json.loads(receipt.read_text())
            record["production_recovery_verified"] = True
            receipt.write_text(json.dumps(record))

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_regression_not_reported_as_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, _, _ = self._records(
                directory, (503, 200, 200, 200, 503)
            )
            summary = audit_measured_receipts(output)

            self.assertEqual(summary["observed_failure"], 1)
            self.assertEqual(summary["observed_success"], 0)

    def test_read_only_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            output, receipt, incident, intent = self._records(directory)
            before = {
                p: p.read_bytes()
                for p in (receipt, incident, intent)
            }

            audit_measured_receipts(output)

            self.assertEqual(
                before,
                {p: p.read_bytes() for p in before},
            )


if __name__ == "__main__":
    unittest.main()


class MeasuredEvidenceAuditTests(unittest.TestCase):

    def _setup(self, directory):
        root = Path(directory)
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()

        evidence_path = write_observation(
            evidence_dir,
            report_for([503, 503, 503, 200, 200, 200]),
        )

        output = root / "records"
        evaluate_measured_receipt(FakeRPC(), evidence_path, output)

        return output, evidence_dir, evidence_path

    def test_evidence_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            output, evidence_dir, _ = self._setup(directory)

            summary = audit_measured_receipts(
                output, evidence_dir=evidence_dir
            )

            self.assertEqual(summary["receipts_verified"], 1)
            self.assertEqual(summary["evidence_files_verified"], 1)
            self.assertEqual(summary["observed_success"], 1)

    def test_tampered_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, evidence_dir, evidence_path = self._setup(directory)
            evidence_path.write_text('{"tampered":true}')

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(
                    output, evidence_dir=evidence_dir
                )

    def test_missing_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, evidence_dir, evidence_path = self._setup(directory)
            evidence_path.unlink()

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(
                    output, evidence_dir=evidence_dir
                )

    def test_evidence_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, evidence_dir, evidence_path = self._setup(directory)
            original = evidence_path.with_suffix(".backup")
            evidence_path.rename(original)
            evidence_path.symlink_to(original)

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(
                    output, evidence_dir=evidence_dir
                )


if __name__ == "__main__":
    unittest.main()


class MeasuredAuditFinalHardeningTests(unittest.TestCase):

    def _setup(self, directory):
        root = Path(directory)
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()

        evidence_path = write_observation(
            evidence_dir,
            report_for([503, 503, 503, 200, 200, 200]),
        )

        output = root / "records"
        evaluate_measured_receipt(FakeRPC(), evidence_path, output)

        return output, evidence_dir, evidence_path

    def test_missing_receipt_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, _ = self._setup(directory)

            receipt = (
                output / "measured_receipts"
                / "run-measured-receipt-p10-integration.json"
            )
            receipt.unlink()

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_empty_receipt_directory_with_completed_incident_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, _ = self._setup(directory)

            receipt_dir = output / "measured_receipts"
            for path in receipt_dir.iterdir():
                path.unlink()

            with self.assertRaises(MeasuredAuditError):
                audit_measured_receipts(output)

    def test_evidence_mutation_after_read_does_not_change_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            output, evidence_dir, evidence_path = self._setup(directory)

            from agent import measured_audit_p12 as module
            from unittest.mock import patch

            real_read = module._read_evidence

            def mutate_after_read(path):
                original = real_read(path)
                evidence_path.write_text('{"tampered":true}')
                return original

            with patch.object(
                module,
                "_read_evidence",
                side_effect=mutate_after_read,
            ):
                summary = audit_measured_receipts(
                    output,
                    evidence_dir=evidence_dir,
                )

            self.assertEqual(summary["receipts_verified"], 1)
            self.assertEqual(summary["evidence_files_verified"], 1)

    def test_unrelated_incident_does_not_count_as_measured_orphan(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, _ = self._setup(directory)

            # P07-style records may coexist with P10 measured records.
            self.assertEqual(
                audit_measured_receipts(output)["receipts_verified"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
