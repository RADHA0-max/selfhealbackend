"""P11 measured evidence receipt and recovery consistency tests."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agent.measured_receipt_p11 import (
    MeasuredReceiptError,
    evaluate_measured_receipt,
)
from agent.tests.test_measured_incident_p10 import FakeRPC, report_for
from chaos.envoy_observer_p09 import write_observation
from agent.durable_offline_incident import IncidentReplayError


class MeasuredReceiptTests(unittest.TestCase):

    def _capture(self, directory, statuses):
        evidence_dir = Path(directory) / "evidence"
        evidence_dir.mkdir()

        return write_observation(
            evidence_dir,
            report_for(statuses),
        )

    def test_realistic_recovery_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._capture(
                directory,
                [503, 503, 503, 200, 200, 200, 200],
            )

            rpc = FakeRPC()
            receipt = evaluate_measured_receipt(
                rpc, path, Path(directory) / "records"
            )

            self.assertEqual(rpc.calls, 1)
            self.assertEqual(
                receipt["evidence_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                receipt["observed_sustained_recovery"], "SUCCESS"
            )
            self.assertEqual(
                receipt["uninterrupted_recovery"], "FAILED"
            )
            self.assertFalse(receipt["mitigation_executed"])
            self.assertFalse(receipt["production_recovery_verified"])

            saved = (
                Path(directory)
                / "records"
                / "measured_receipts"
                / "run-measured-receipt-p10-integration.json"
            )

            self.assertEqual(json.loads(saved.read_text()), receipt)

    def test_threshold_four_requires_four_healthy_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._capture(
                directory,
                [503, 200, 200, 200],
            )
            rpc = FakeRPC()

            with self.assertRaises(MeasuredReceiptError):
                evaluate_measured_receipt(
                    rpc, path, Path(directory) / "records",
                    required_healthy=4,
                )

            self.assertEqual(rpc.calls, 0)

    def test_threshold_four_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._capture(
                directory,
                [503, 200, 200, 200, 200],
            )

            receipt = evaluate_measured_receipt(
                FakeRPC(),
                path,
                Path(directory) / "records",
                required_healthy=4,
            )

            self.assertEqual(
                receipt["observed_sustained_recovery"], "SUCCESS"
            )
            self.assertEqual(receipt["required_healthy"], 4)

    def test_regression_after_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._capture(
                directory,
                [503, 200, 200, 200, 503],
            )

            receipt = evaluate_measured_receipt(
                FakeRPC(),
                path,
                Path(directory) / "records",
            )

            self.assertEqual(
                receipt["observed_sustained_recovery"], "FAILED"
            )
            self.assertEqual(
                receipt["uninterrupted_recovery"], "FAILED"
            )

    def test_replay_never_calls_model_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._capture(
                directory,
                [503, 200, 200, 200],
            )
            rpc = FakeRPC()
            output = Path(directory) / "records"

            evaluate_measured_receipt(rpc, path, output)

            with self.assertRaises(IncidentReplayError):
                evaluate_measured_receipt(rpc, path, output)

            self.assertEqual(rpc.calls, 1)

    def test_invalid_threshold_never_calls_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._capture(
                directory,
                [503, 200, 200, 200],
            )
            rpc = FakeRPC()

            for threshold in (True, 1, 11, 3.0, "3"):
                with self.assertRaises(MeasuredReceiptError):
                    evaluate_measured_receipt(
                        rpc,
                        path,
                        Path(directory) / "records",
                        required_healthy=threshold,
                    )

            self.assertEqual(rpc.calls, 0)


if __name__ == "__main__":
    unittest.main()
