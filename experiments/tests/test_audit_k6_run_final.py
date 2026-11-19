"""Offline integration tests for runner receipt and Envoy reconciliation."""

import json
import tempfile
import unittest
from pathlib import Path

from experiments.audit_k6_run_final import audit
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class AuditK6RunTests(unittest.TestCase):
    def setUp(self):
        from experiments.tests.test_verify_traffic_final import VerifyTrafficTests

        self.fixture = VerifyTrafficTests(
            methodName="test_1200_request_end_to_end"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self.root)
        )

        self.run_id = self.fixture.run_id
        self.capture = self.root / f"{self.run_id}.jsonl"
        self.reservation = self.root / f"{self.run_id}.reserved"
        self.reservation.mkdir()

    def setup_run(self, count=1200, status="CAPTURE_PARSED"):
        self.fixture.write_fixture(count=count)
        self.capture.write_bytes(self.fixture.k6.read_bytes())

        receipt = {
            "run_id": self.run_id,
            "status": status,
            "capture": str(self.capture),
            "request_count": count,
            "capture_complete_verified": False,
            "runtime_origin_verified": False,
            "source_ip_verified": False,
        }

        (self.reservation / "status.json").write_text(
            json.dumps(receipt) + "\n"
        )

    def test_complete_reconciled_run(self):
        self.setup_run()
        result = audit(
            self.run_id,
            self.fixture.envoy,
            self.root,
        )
        self.assertEqual(
            result["audit_status"],
            "EVIDENCE_RECONCILED",
        )
        self.assertEqual(result["request_count"], 1200)
        self.assertTrue(result["request_ids_match"])
        self.assertFalse(result["runtime_origin_verified"])

    def test_failed_runner_rejected(self):
        self.setup_run(status="K6_FAILED")
        with self.assertRaises(TrafficEvidenceError):
            audit(self.run_id, self.fixture.envoy, self.root)

    def test_partial_run_rejected_by_default(self):
        self.setup_run(count=20)
        with self.assertRaises(TrafficEvidenceError):
            audit(self.run_id, self.fixture.envoy, self.root)

    def test_partial_run_allowed_explicitly(self):
        self.setup_run(count=20)
        result = audit(
            self.run_id,
            self.fixture.envoy,
            self.root,
            allow_partial=True,
        )
        self.assertEqual(result["workload_status"], "PARTIAL")
        self.assertFalse(result["scheduled_iterations_complete"])

    def test_missing_receipt_rejected(self):
        self.setup_run()
        (self.reservation / "status.json").unlink()
        with self.assertRaises(OSError):
            audit(self.run_id, self.fixture.envoy, self.root)

    def test_receipt_count_mismatch_rejected(self):
        self.setup_run(count=20)
        path = self.reservation / "status.json"
        receipt = json.loads(path.read_text())
        receipt["request_count"] = 19
        path.write_text(json.dumps(receipt) + "\n")

        with self.assertRaises(TrafficEvidenceError):
            audit(
                self.run_id,
                self.fixture.envoy,
                self.root,
                allow_partial=True,
            )


if __name__ == "__main__":
    unittest.main()
