"""Offline audit export integrity regression tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.export_archived_audit_final import export_report
from experiments.verify_exported_audit_final import verify_export


class ExportedAuditTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audit_dir = self.root / "audits"
        self.run_id = "audit-test"

        self.report = {
            "schema": "nanoclaw.archived-offline-audit.v1",
            "run_id": self.run_id,
            "audit_status": "OFFLINE_RECONCILED_UNATTESTED",
            "audit": {
                "request_ids_match": True,
                "k6_manifest_count": 2,
                "envoy_event_count": 2,
            },
            "evidence_files": {},
            "limitations": {
                "capture_completeness_verified": False,
            },
        }

    def export(self):
        with patch(
            "experiments.export_archived_audit_final.build_report",
            return_value=self.report,
        ):
            return export_report(
                self.run_id,
                self.root,
                self.audit_dir,
            )

    def test_export_and_verify(self):
        self.export()

        with patch(
            "experiments.verify_exported_audit_final.build_report",
            return_value=self.report,
        ):
            result = verify_export(
                self.run_id,
                self.root,
                self.audit_dir,
            )

        self.assertTrue(result["report_verified"])

    def test_reject_tampered_export(self):
        self.export()

        path = self.audit_dir / (
            self.run_id + ".offline-audit.json"
        )

        report = json.loads(path.read_text())
        report["audit"]["request_ids_match"] = False
        path.write_text(json.dumps(report))

        with patch(
            "experiments.verify_exported_audit_final.build_report",
            return_value=self.report,
        ):
            with self.assertRaises(ValueError):
                verify_export(
                    self.run_id,
                    self.root,
                    self.audit_dir,
                )

    def test_export_does_not_overwrite(self):
        self.export()

        with self.assertRaises(FileExistsError):
            self.export()

    def test_reject_missing_report(self):
        with self.assertRaises(FileNotFoundError):
            verify_export(
                self.run_id,
                self.root,
                self.audit_dir,
            )


if __name__ == "__main__":
    unittest.main()


class AdditionalExportSafetyTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audit_dir = self.root / "audits"
        self.run_id = "atomic-test"
        self.report = {
            "schema": "nanoclaw.archived-offline-audit.v1",
            "run_id": self.run_id,
            "audit_status": "OFFLINE_RECONCILED_UNATTESTED",
            "audit": {"request_ids_match": True},
            "evidence_files": {},
            "limitations": {},
        }

    def run_export(self):
        with patch(
            "experiments.export_archived_audit_final.build_report",
            return_value=self.report,
        ):
            return export_report(
                self.run_id,
                self.root,
                self.audit_dir,
            )

    def test_atomic_export_no_temp_leftovers(self):
        self.run_export()

        files = list(self.audit_dir.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(
            files[0].name,
            self.run_id + ".offline-audit.json",
        )

    def test_existing_report_unchanged(self):
        self.run_export()

        output = self.audit_dir / (
            self.run_id + ".offline-audit.json"
        )
        before = output.read_bytes()

        with self.assertRaises(FileExistsError):
            self.run_export()

        self.assertEqual(output.read_bytes(), before)

    def test_symlink_target_not_followed(self):
        self.audit_dir.mkdir()
        target = self.root / "outside.txt"
        target.write_text("do-not-touch")

        output = self.audit_dir / (
            self.run_id + ".offline-audit.json"
        )
        output.symlink_to(target)

        with self.assertRaises(FileExistsError):
            self.run_export()

        self.assertEqual(target.read_text(), "do-not-touch")


class CanonicalAuditTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audit_dir = self.root / "audits"
        self.run_id = "canonical-test"

        self.report = {
            "schema": "nanoclaw.archived-offline-audit.v1",
            "run_id": self.run_id,
            "audit_status": "OFFLINE_RECONCILED_UNATTESTED",
            "audit": {"request_ids_match": True},
            "evidence_files": {},
            "limitations": {},
        }

        with patch(
            "experiments.export_archived_audit_final.build_report",
            return_value=self.report,
        ):
            export_report(
                self.run_id,
                self.root,
                self.audit_dir,
            )

        self.path = self.audit_dir / (
            self.run_id + ".offline-audit.json"
        )

    def verify(self):
        with patch(
            "experiments.verify_exported_audit_final.build_report",
            return_value=self.report,
        ):
            return verify_export(
                self.run_id,
                self.root,
                self.audit_dir,
            )

    def test_canonical_export_passes(self):
        self.assertTrue(self.verify()["report_verified"])

    def test_reject_reformatted_json(self):
        original = json.loads(self.path.read_text())
        self.path.write_text(json.dumps(original))
        with self.assertRaises(ValueError):
            self.verify()

    def test_reject_trailing_whitespace(self):
        self.path.write_bytes(
            self.path.read_bytes() + b" "
        )
        with self.assertRaises(ValueError):
            self.verify()
