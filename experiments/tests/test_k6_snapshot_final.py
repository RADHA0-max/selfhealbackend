"""Offline tests for bounded k6 capture integrity."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.k6_snapshot_final import (
    assert_unchanged,
    fingerprint,
)
from experiments.collect_run_evidence_final import collect
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class K6SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "capture.jsonl"
        self.path.write_bytes(b'{"type":"Point"}\n')

    def test_stable_capture(self):
        before = fingerprint(self.path)
        self.assertEqual(assert_unchanged(self.path, before), before)

    def test_mutated_capture_rejected(self):
        before = fingerprint(self.path)
        self.path.write_bytes(b'{"type":"Other"}\n')
        with self.assertRaises(TrafficEvidenceError):
            assert_unchanged(self.path, before)

    def test_replaced_capture_rejected(self):
        before = fingerprint(self.path)
        replacement = self.path.with_suffix(".new")
        replacement.write_bytes(self.path.read_bytes())
        replacement.replace(self.path)

        with self.assertRaises(TrafficEvidenceError):
            assert_unchanged(self.path, before)

    def test_symlink_rejected(self):
        link = self.path.with_suffix(".link")
        link.symlink_to(self.path)

        with self.assertRaises(OSError):
            fingerprint(link)

    def test_empty_capture_rejected(self):
        self.path.write_bytes(b"")

        with self.assertRaises(TrafficEvidenceError):
            fingerprint(self.path)


class CollectionSnapshotTests(unittest.TestCase):
    def setUp(self):
        from experiments.tests.test_collect_run_evidence_final import (
            CollectRunEvidenceTests,
        )

        self.fixture = CollectRunEvidenceTests(
            methodName="test_prepare_has_no_docker_access"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_capture_mutation_during_docker_rejected(self):
        self.fixture.setup_run(count=20)

        def mutate(*args, **kwargs):
            self.fixture.capture.write_bytes(
                self.fixture.capture.read_bytes() + b"\n"
            )
            return {
                "request_reconciliation": {
                    "request_ids_match": True,
                },
                "docker_capture_sha256": "a" * 64,
            }

        with patch(
            "experiments.collect_run_evidence_final.capture_envoy_logs",
            side_effect=mutate,
        ):
            with self.assertRaises(TrafficEvidenceError):
                collect(
                    self.fixture.run_id,
                    self.fixture.root,
                    "nanoclaw-testbed-envoy",
                    self.fixture.since,
                    self.fixture.until,
                    require_complete=False,
                )

        self.assertFalse(
            (
                self.fixture.reservation / "envoy-evidence.json"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
