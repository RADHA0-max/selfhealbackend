"""Offline evidence receipt integrity tests."""

import json
import unittest
from unittest.mock import patch

from experiments.audit_collected_evidence_final import audit_collected
from experiments.collect_run_evidence_final import collect
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class CollectedEvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        from experiments.tests.test_collect_run_evidence_final import (
            CollectRunEvidenceTests,
        )

        self.fixture = CollectRunEvidenceTests(
            methodName="test_prepare_has_no_docker_access"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def make_receipt(self, count=1200):
        self.fixture.setup_run(count=count)

        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs",
            return_value={
                "request_reconciliation": {
                    "request_ids_match": True,
                },
                "docker_capture_sha256": "a" * 64,
            "validated_event_count": count,
            "ignored_non_json_messages": 0,
            },
        ):
            collect(
                self.fixture.run_id,
                self.fixture.root,
                "nanoclaw-testbed-envoy",
                self.fixture.since,
                self.fixture.until,
                require_complete=count == 1200,
            )

    def test_complete_receipt_integrity(self):
        self.make_receipt()

        result = audit_collected(
            self.fixture.run_id,
            self.fixture.root,
        )

        self.assertEqual(result["request_count"], 1200)
        self.assertTrue(result["receipt_integrity_verified"])
        self.assertFalse(result["envoy_raw_capture_reverified"])

    def test_partial_rejected_by_default(self):
        self.make_receipt(count=20)

        with self.assertRaises(TrafficEvidenceError):
            audit_collected(
                self.fixture.run_id,
                self.fixture.root,
            )

    def test_partial_allowed_explicitly(self):
        self.make_receipt(count=20)

        result = audit_collected(
            self.fixture.run_id,
            self.fixture.root,
            allow_partial=True,
        )

        self.assertEqual(result["workload_status"], "PARTIAL")

    def test_capture_mutation_rejected(self):
        self.make_receipt(count=20)

        self.fixture.capture.write_bytes(
            self.fixture.capture.read_bytes() + b"\n"
        )

        with self.assertRaises(TrafficEvidenceError):
            audit_collected(
                self.fixture.run_id,
                self.fixture.root,
                allow_partial=True,
            )

    def test_tampered_digest_rejected(self):
        self.make_receipt(count=20)

        path = self.fixture.reservation / "envoy-evidence.json"
        receipt = json.loads(path.read_text())
        receipt["k6_capture_sha256"] = "0" * 64
        path.write_text(json.dumps(receipt) + "\n")

        with self.assertRaises(TrafficEvidenceError):
            audit_collected(
                self.fixture.run_id,
                self.fixture.root,
                allow_partial=True,
            )

    def test_forged_runtime_claim_rejected(self):
        self.make_receipt(count=20)

        path = self.fixture.reservation / "envoy-evidence.json"
        receipt = json.loads(path.read_text())
        receipt["runtime_origin_verified"] = True
        path.write_text(json.dumps(receipt) + "\n")

        with self.assertRaises(TrafficEvidenceError):
            audit_collected(
                self.fixture.run_id,
                self.fixture.root,
                allow_partial=True,
            )


if __name__ == "__main__":
    unittest.main()
