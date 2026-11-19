"""Offline integration tests for explicit Envoy evidence collection."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.collect_run_evidence_final import collect, prepare
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class CollectRunEvidenceTests(unittest.TestCase):
    def setUp(self):
        from experiments.tests.test_verify_traffic_final import VerifyTrafficTests

        self.fixture = VerifyTrafficTests(
            methodName="test_1200_request_end_to_end"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.run_id = self.fixture.run_id
        self.capture = self.root / f"{self.run_id}.jsonl"
        self.reservation = self.root / f"{self.run_id}.reserved"
        self.reservation.mkdir()

        self.since = "2026-11-19T00:00:00Z"
        self.until = "2026-11-19T00:01:00Z"

    def setup_run(self, count=1200, status="CAPTURE_PARSED"):
        self.fixture.write_fixture(count=count)
        self.capture.write_bytes(self.fixture.k6.read_bytes())
        (self.reservation / "status.json").write_text(
            json.dumps({
                "run_id": self.run_id,
                "status": status,
                "capture": str(self.capture),
                "request_count": count,
            }) + "\n"
        )

    def test_prepare_has_no_docker_access(self):
        self.setup_run(count=20)
        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs"
        ) as docker:
            result = prepare(self.run_id, self.root)
            docker.assert_not_called()
        self.assertEqual(result["request_count"], 20)

    def test_failed_runner_rejected(self):
        self.setup_run(status="K6_FAILED")
        with self.assertRaises(TrafficEvidenceError):
            prepare(self.run_id, self.root)

    def test_reconciled_evidence_receipt(self):
        self.setup_run(count=20)
        fake_report = {
            "request_reconciliation": {"request_ids_match": True},
            "docker_capture_sha256": "a" * 64,
            "validated_event_count": 20,
            "ignored_non_json_messages": 0,
        }
        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs",
            return_value=fake_report,
        ) as docker:
            result = collect(
                self.run_id, self.root, "nanoclaw-testbed-envoy",
                self.since, self.until,
            )
        docker.assert_called_once()
        self.assertEqual(result["evidence_status"], "RECONCILED_UNATTESTED")
        self.assertFalse(result["runtime_origin_verified"])
        self.assertTrue(
            (self.reservation / "envoy-evidence.json").is_file()
        )

    def test_mismatched_evidence_rejected(self):
        self.setup_run(count=20)
        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs",
            return_value={
                "request_reconciliation": {"request_ids_match": False},
                "docker_capture_sha256": "a" * 64,
            "validated_event_count": 20,
            "ignored_non_json_messages": 0,
            },
        ):
            with self.assertRaises(TrafficEvidenceError):
                collect(
                    self.run_id, self.root, "nanoclaw-testbed-envoy",
                    self.since, self.until,
                )
        self.assertFalse(
            (self.reservation / "envoy-evidence.json").exists()
        )

    def test_receipt_cannot_be_overwritten(self):
        self.setup_run(count=20)
        (self.reservation / "envoy-evidence.json").write_text("existing")
        with self.assertRaises(TrafficEvidenceError):
            prepare(self.run_id, self.root)

    def test_invalid_window_rejected_before_docker(self):
        self.setup_run(count=20)
        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs"
        ) as docker:
            with self.assertRaises(TrafficEvidenceError):
                collect(
                    self.run_id, self.root, "nanoclaw-testbed-envoy",
                    self.until, self.since,
                )
            docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
