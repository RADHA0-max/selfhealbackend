"""Strict collector policy and bounded request-ID validation."""

import unittest
from unittest.mock import patch

from experiments.collect_run_evidence_final import collect, prepare
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class StrictCollectionTests(unittest.TestCase):
    def setUp(self):
        from experiments.tests.test_collect_run_evidence_final import (
            CollectRunEvidenceTests,
        )

        self.fixture = CollectRunEvidenceTests(
            methodName="test_prepare_has_no_docker_access"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_complete_workload_accepted(self):
        self.fixture.setup_run(count=1200)
        report = prepare(self.fixture.run_id, self.fixture.root)

        self.assertTrue(report["scheduled_iterations_complete"])
        self.assertEqual(report["missing_scheduled_iterations"], 0)

    def test_partial_workload_detected(self):
        self.fixture.setup_run(count=20)
        report = prepare(self.fixture.run_id, self.fixture.root)

        self.assertFalse(report["scheduled_iterations_complete"])
        self.assertEqual(report["missing_scheduled_iterations"], 1180)

    def test_partial_rejected_before_docker_capture(self):
        self.fixture.setup_run(count=20)

        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs"
        ) as docker:
            with self.assertRaises(TrafficEvidenceError):
                collect(
                    self.fixture.run_id,
                    self.fixture.root,
                    "nanoclaw-testbed-envoy",
                    self.fixture.since,
                    self.fixture.until,
                    require_complete=True,
                )
            docker.assert_not_called()

    def test_complete_workload_reaches_collector(self):
        self.fixture.setup_run(count=1200)

        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs",
            return_value={
                "request_reconciliation": {
                    "request_ids_match": True,
                },
                "docker_capture_sha256": "a" * 64,
            "validated_event_count": 1200,
            "ignored_non_json_messages": 0,
            },
        ) as docker:
            receipt = collect(
                self.fixture.run_id,
                self.fixture.root,
                "nanoclaw-testbed-envoy",
                self.fixture.since,
                self.fixture.until,
                require_complete=True,
            )

        docker.assert_called_once()
        self.assertEqual(receipt["workload_status"], "COMPLETE")
        self.assertTrue(receipt["scheduled_iterations_complete"])

    def test_partial_explicitly_labelled(self):
        self.fixture.setup_run(count=20)

        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs",
            return_value={
                "request_reconciliation": {
                    "request_ids_match": True,
                },
                "docker_capture_sha256": "a" * 64,
            "validated_event_count": 20,
            "ignored_non_json_messages": 0,
            },
        ):
            receipt = collect(
                self.fixture.run_id,
                self.fixture.root,
                "nanoclaw-testbed-envoy",
                self.fixture.since,
                self.fixture.until,
                require_complete=False,
            )

        self.assertEqual(receipt["workload_status"], "PARTIAL")
        self.assertEqual(receipt["missing_scheduled_iterations"], 1180)
        self.assertFalse(receipt["capture_completeness_verified"])


if __name__ == "__main__":
    unittest.main()
