"""Fail-closed metadata contract for collected Envoy evidence."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.collect_run_evidence_final import collect
from experiments.audit_collected_evidence_final import audit_collected
from experiments.traffic_evidence_p15 import TrafficEvidenceError
from experiments.tests import test_collect_run_evidence_final as collect_fixture


class EvidenceMetadataContractTests(unittest.TestCase):
    def setUp(self):
        self.base = collect_fixture.CollectRunEvidenceTests(
            methodName="test_reconciled_evidence_receipt"
        )
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.setup_run(count=20)

    def collect_with(self, report):
        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs",
            return_value=report,
        ):
            return collect(
                self.base.run_id,
                self.base.root,
                "nanoclaw-testbed-envoy",
                self.base.since,
                self.base.until,
            )

    def valid_report(self):
        return {
            "request_reconciliation": {
                "request_ids_match": True,
            },
            "docker_capture_sha256": "a" * 64,
            "validated_event_count": 20,
            "ignored_non_json_messages": 0,
        }

    def assert_rejected_without_receipt(self, report):
        with self.assertRaises(TrafficEvidenceError):
            self.collect_with(report)

        self.assertFalse(
            (
                self.base.reservation / "envoy-evidence.json"
            ).exists()
        )

    def test_missing_event_count_rejected(self):
        report = self.valid_report()
        del report["validated_event_count"]
        self.assert_rejected_without_receipt(report)

    def test_missing_ignored_message_count_rejected(self):
        report = self.valid_report()
        del report["ignored_non_json_messages"]
        self.assert_rejected_without_receipt(report)

    def test_incorrect_event_count_rejected(self):
        report = self.valid_report()
        report["validated_event_count"] = 19
        self.assert_rejected_without_receipt(report)

    def test_negative_ignored_message_count_rejected(self):
        report = self.valid_report()
        report["ignored_non_json_messages"] = -1
        self.assert_rejected_without_receipt(report)

    def test_boolean_event_count_rejected(self):
        report = self.valid_report()
        report["validated_event_count"] = True
        self.assert_rejected_without_receipt(report)

    def test_boolean_ignored_count_rejected(self):
        report = self.valid_report()
        report["ignored_non_json_messages"] = False
        self.assert_rejected_without_receipt(report)

    def test_valid_metadata_receipt_audits(self):
        self.collect_with(self.valid_report())

        result = audit_collected(
            self.base.run_id,
            self.base.root,
            allow_partial=True,
        )
        self.assertEqual(
            result["audit_status"],
            "RECEIPT_INTEGRITY_VERIFIED",
        )

    def test_tampered_event_count_rejected_by_auditor(self):
        self.collect_with(self.valid_report())

        receipt_path = (
            self.base.reservation / "envoy-evidence.json"
        )
        receipt = json.loads(receipt_path.read_text())
        receipt["envoy_validated_event_count"] = 19
        receipt_path.write_text(
            json.dumps(receipt) + "\n"
        )

        with self.assertRaises(TrafficEvidenceError):
            audit_collected(
                self.base.run_id,
                self.base.root,
                allow_partial=True,
            )


if __name__ == "__main__":
    unittest.main()
