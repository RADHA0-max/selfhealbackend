"""Adversarial tests for archived evidence receipt validation."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import reconcile_archived_run_final as audit
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class ReceiptGuardTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_id = "guard-test"

        self.k6_path = self.root / (self.run_id + ".jsonl")
        self.envoy_path = self.root / (
            self.run_id + ".envoy-docker-stdout.log"
        )
        self.receipt_path = self.root / (
            self.run_id + ".reserved/envoy-evidence.json"
        )
        self.manifest_path = self.root / (
            self.run_id + ".raw-capture-verification.json"
        )

        self.receipt_path.parent.mkdir()

        k6 = {
            "type": "Point",
            "metric": "nanoclaw_request_manifest",
            "data": {
                "value": 1,
                "tags": {
                    "workload": "organic_60vu",
                    "request_id": "guard-1",
                },
            },
        }

        self.k6_path.write_bytes(
            (json.dumps(k6) + "\n").encode()
        )

        event = {
            "timestamp": "2026-11-19T04:24:01+00:00",
            "client_ip": "172.20.0.5",
            "method": "GET",
            "path": "/health",
            "status": 200,
            "duration_ms": 1,
            "user_agent": "guard-test",
            "request_id": "guard-1",
        }

        self.envoy_path.write_bytes(
            (
                "2026-11-19T04:24:02.000000000Z "
                + json.dumps(event)
                + "\n"
            ).encode()
        )

        self.receipt = {
            "schema": "nanoclaw.envoy-evidence.final.v1",
            "run_id": self.run_id,
            "evidence_status": "RECONCILED_UNATTESTED",
            "k6_capture_sha256": audit.sha256(
                self.k6_path.read_bytes()
            ),
            "docker_capture_sha256": audit.sha256(
                self.envoy_path.read_bytes()
            ),
            "request_count": 1,
            "envoy_validated_event_count": 1,
            "request_ids_match": True,
            "scheduled_iterations_complete": True,
            "missing_scheduled_iterations": 0,
            "scheduled_iterations": 1,
            "workload_status": "COMPLETE",
            "since": "2026-11-19T04:24:00Z",
            "until": "2026-11-19T04:25:00Z",
        }

        self.manifest = {
            "schema": "nanoclaw.raw-capture-verification.v1",
            "run_id": self.run_id,
            "archive_sha256": audit.sha256(
                self.envoy_path.read_bytes()
            ),
            "raw_capture_sha256_matches_receipt": True,
            "receipt_integrity_verified": True,
            "request_ids_match": True,
            "raw_stdout_records": 1,
            "capture_window": {
                "since": self.receipt["since"],
                "until": self.receipt["until"],
            },
        }

        # The production Envoy parser requires at least two events.
        # Extend the fixture without relaxing production validation.
        k6_second = {
            "type": "Point",
            "metric": "nanoclaw_request_manifest",
            "data": {
                "value": 1,
                "tags": {
                    "workload": "organic_60vu",
                    "request_id": "guard-2",
                },
            },
        }

        with self.k6_path.open("ab") as stream:
            stream.write((json.dumps(k6_second) + "\n").encode())

        event_second = dict(event)
        event_second["request_id"] = "guard-2"
        event_second["timestamp"] = "2026-11-19T04:24:03+00:00"

        with self.envoy_path.open("ab") as stream:
            stream.write(
                (
                    "2026-11-19T04:24:04.000000000Z "
                    + json.dumps(event_second)
                    + "\n"
                ).encode()
            )

        self.receipt["k6_capture_sha256"] = audit.sha256(
            self.k6_path.read_bytes()
        )
        self.receipt["docker_capture_sha256"] = audit.sha256(
            self.envoy_path.read_bytes()
        )
        self.receipt["request_count"] = 2
        self.receipt["envoy_validated_event_count"] = 2
        self.receipt["scheduled_iterations"] = 2

        self.manifest["archive_sha256"] = audit.sha256(
            self.envoy_path.read_bytes()
        )
        self.manifest["raw_stdout_records"] = 2

        self.save()

    def save(self):
        self.receipt_path.write_text(
            json.dumps(self.receipt, sort_keys=True)
        )
        self.manifest["receipt_sha256"] = audit.sha256(
            self.receipt_path.read_bytes()
        )
        self.manifest_path.write_text(
            json.dumps(self.manifest, sort_keys=True)
        )

    def assert_rejected(self):
        with self.assertRaises(TrafficEvidenceError):
            audit.verify(self.run_id, self.root)

    def test_valid_receipt(self):
        result = audit.verify(self.run_id, self.root)
        self.assertTrue(result["fresh_request_id_reconciliation"])

    def test_reject_wrong_receipt_schema(self):
        self.receipt["schema"] = "untrusted"
        self.save()
        self.assert_rejected()

    def test_reject_wrong_manifest_schema(self):
        self.manifest["schema"] = "untrusted"
        self.save()
        self.assert_rejected()

    def test_reject_incomplete_workload(self):
        self.receipt["workload_status"] = "PARTIAL"
        self.save()
        self.assert_rejected()

    def test_reject_missing_iteration(self):
        self.receipt["missing_scheduled_iterations"] = 1
        self.save()
        self.assert_rejected()

    def test_reject_false_reconciliation(self):
        self.manifest["request_ids_match"] = False
        self.save()
        self.assert_rejected()

    def test_reject_unverified_receipt(self):
        self.manifest["receipt_integrity_verified"] = False
        self.save()
        self.assert_rejected()

    def test_reject_wrong_scheduled_count(self):
        self.receipt["scheduled_iterations"] = 3
        self.save()
        self.assert_rejected()

    def test_reject_wrong_evidence_status(self):
        self.receipt["evidence_status"] = "ATTESTED"
        self.save()
        self.assert_rejected()

    def test_reject_tampered_k6_capture(self):
        self.k6_path.write_bytes(
            self.k6_path.read_bytes() + b"x"
        )
        self.assert_rejected()

    def test_reject_tampered_envoy_archive(self):
        self.envoy_path.write_bytes(
            self.envoy_path.read_bytes() + b"x"
        )
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
