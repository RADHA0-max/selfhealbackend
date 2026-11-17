"""P11 adversarial evidence integrity and durable lifecycle tests."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.durable_offline_incident import IncidentReplayError
from agent.measured_incident_p10 import MeasuredIncidentError
from agent.measured_receipt_p11 import (
    MeasuredReceiptError,
    evaluate_measured_receipt,
)
from agent.tests.test_measured_incident_p10 import FakeRPC, report_for
from chaos.envoy_observer_p09 import write_observation


class MeasuredReceiptSecurityTests(unittest.TestCase):

    def capture(self, directory, statuses=(503, 200, 200, 200)):
        evidence_dir = Path(directory) / "evidence"
        evidence_dir.mkdir()
        return write_observation(
            evidence_dir,
            report_for(list(statuses)),
        )

    def test_original_mutation_after_snapshot_does_not_change_diagnosis(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(directory)
            original = path.read_bytes()
            original_hash = hashlib.sha256(original).hexdigest()
            rpc = FakeRPC()

            from agent import measured_receipt_p11 as module
            real_evaluate = module.evaluate_measured_incident

            def mutate_then_evaluate(rpc_arg, snapshot, output, **kwargs):
                path.write_text('{"tampered":true}')
                return real_evaluate(
                    rpc_arg, snapshot, output, **kwargs
                )

            with patch.object(
                module,
                "evaluate_measured_incident",
                side_effect=mutate_then_evaluate,
            ):
                receipt = evaluate_measured_receipt(
                    rpc, path, Path(directory) / "records"
                )

            self.assertEqual(receipt["evidence_sha256"], original_hash)
            self.assertEqual(rpc.calls, 1)
            self.assertEqual(
                receipt["observed_sustained_recovery"], "SUCCESS"
            )

    def test_symlink_rejected_before_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(directory)
            link = Path(directory) / "linked.json"
            link.symlink_to(path)
            rpc = FakeRPC()

            with self.assertRaises(MeasuredReceiptError):
                evaluate_measured_receipt(
                    rpc, link, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)

    def test_oversized_evidence_rejected_before_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(directory)
            path.write_bytes(b"x" * 65537)
            rpc = FakeRPC()

            with self.assertRaises(MeasuredReceiptError):
                evaluate_measured_receipt(
                    rpc, path, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)

    def test_duplicate_json_keys_rejected_before_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(directory)
            path.write_text(
                '{"experiment_id":"p10-integration",'
                '"experiment_id":"p10-integration"}'
            )
            rpc = FakeRPC()

            with self.assertRaises(MeasuredIncidentError):
                evaluate_measured_receipt(
                    rpc, path, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)

    def test_invalid_filename_rejected_before_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(directory)
            renamed = path.with_name("incorrect.json")
            path.rename(renamed)
            rpc = FakeRPC()

            with self.assertRaises(MeasuredReceiptError):
                evaluate_measured_receipt(
                    rpc, renamed, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)

    def test_timeout_persists_intent_and_blocks_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(directory)
            output = Path(directory) / "records"
            rpc = FakeRPC(failure=TimeoutError("uncertain RPC"))

            with self.assertRaises(TimeoutError):
                evaluate_measured_receipt(rpc, path, output)

            intent = (
                output
                / "offline_incidents"
                / "run-offline-incident-p10-integration-0-intent.json"
            )
            self.assertTrue(intent.is_file())

            with self.assertRaises(IncidentReplayError):
                evaluate_measured_receipt(rpc, path, output)

            self.assertEqual(rpc.calls, 1)

    def test_regression_after_sustained_recovery_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(
                directory,
                (503, 503, 200, 200, 200, 503, 200),
            )

            receipt = evaluate_measured_receipt(
                FakeRPC(), path, Path(directory) / "records"
            )

            self.assertEqual(
                receipt["observed_sustained_recovery"], "FAILED"
            )
            self.assertFalse(receipt["production_recovery_verified"])

    def test_healthy_baseline_never_calls_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(
                directory, (200, 200, 200, 200)
            )
            rpc = FakeRPC()

            with self.assertRaises(MeasuredIncidentError):
                evaluate_measured_receipt(
                    rpc, path, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)


if __name__ == "__main__":
    unittest.main()


class MeasuredReceiptPersistenceTests(unittest.TestCase):

    def test_receipt_links_to_persisted_incident(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_dir = Path(directory) / "evidence"
            evidence_dir.mkdir()
            path = write_observation(
                evidence_dir,
                report_for([503, 200, 200, 200]),
            )
            output = Path(directory) / "records"

            receipt = evaluate_measured_receipt(FakeRPC(), path, output)

            incident_path = (
                output / "offline_incidents"
                / "run-offline-incident-p10-integration-0.json"
            )
            incident = json.loads(incident_path.read_text())

            canonical = json.dumps(
                incident,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")

            self.assertEqual(
                receipt["incident_sha256"],
                hashlib.sha256(canonical).hexdigest(),
            )

    def test_receipt_write_failure_does_not_repeat_diagnosis(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_dir = Path(directory) / "evidence"
            evidence_dir.mkdir()
            path = write_observation(
                evidence_dir,
                report_for([503, 200, 200, 200]),
            )
            output = Path(directory) / "records"
            rpc = FakeRPC()

            from agent import measured_receipt_p11 as module

            with patch.object(
                module,
                "write_run_record",
                side_effect=OSError("simulated disk failure"),
            ):
                with self.assertRaises(OSError):
                    evaluate_measured_receipt(rpc, path, output)

            with self.assertRaises(IncidentReplayError):
                evaluate_measured_receipt(rpc, path, output)

            self.assertEqual(rpc.calls, 1)
