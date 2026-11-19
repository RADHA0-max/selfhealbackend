"""Offline integration tests for Docker → Envoy → manifest reconciliation."""

import json
import unittest
from unittest.mock import patch

from experiments.docker_envoy_capture_final import capture_envoy_logs
from experiments.tests.test_envoy_evidence_final import sample
from experiments.traffic_evidence_p15 import TrafficEvidenceError

SINCE = "2026-11-16T11:59:00Z"
UNTIL = "2026-11-16T12:01:00Z"
CONTAINER = "nanoclaw-testbed-envoy"


def fixture():
    records = [json.loads(line) for line in sample().splitlines()]
    ids = [record["request_id"] for record in records]
    prefix = b"2026-11-16T12:00:00.123456789Z "
    raw = b"".join(prefix + line + b"\n" for line in sample().splitlines())
    return raw, ids


class FakeStream:
    def __init__(self, data):
        self.data = data
        self.closed = False

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, raw, returncode=0):
        self.stdout = FakeStream(raw)
        self.stderr = FakeStream(b"")
        self.returncode = returncode
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True


class TestDockerCaptureIntegrationFinal(unittest.TestCase):

    def run_capture(self, raw, ids, returncode=0):
        proc = FakeProcess(raw, returncode=returncode)

        with patch(
            "experiments.docker_envoy_capture_final.subprocess.Popen",
            return_value=proc,
        ) as popen, patch(
            "experiments.docker_envoy_capture_final._bounded_read_process",
            return_value=raw,
        ):
            result = capture_envoy_logs(
                CONTAINER,
                since=SINCE,
                until=UNTIL,
                expected_request_ids=ids,
            )

        command = popen.call_args.args[0]
        self.assertEqual(command[0:2], ["docker", "logs"])
        self.assertIn("--timestamps", command)
        self.assertIn("--since", command)
        self.assertIn("--until", command)
        self.assertEqual(command[-1], CONTAINER)
        return result

    def test_complete_capture_and_manifest(self):
        raw, ids = fixture()
        result = self.run_capture(raw, ids)
        reconciliation = result["request_reconciliation"]

        self.assertTrue(reconciliation["request_ids_match"])
        self.assertEqual(reconciliation["expected_request_count"], len(ids))
        self.assertFalse(reconciliation["capture_completeness_verified"])
        self.assertFalse(result["runtime_origin_verified"])

    def test_reject_missing_request(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            self.run_capture(raw, ids[:-1])

    def test_reject_unexpected_request(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            self.run_capture(raw, ids + ["unexpected"])

    def test_reject_duplicate_expected_request(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            self.run_capture(raw, ids + [ids[0]])

    def test_reject_outside_window(self):
        raw, ids = fixture()
        modified = raw.replace(
            b"2026-11-16T12:00:00.123456789Z",
            b"2026-11-16T12:03:00.123456789Z",
        )
        with self.assertRaises(TrafficEvidenceError):
            self.run_capture(modified, ids)

    def test_reject_invalid_docker_timestamp(self):
        raw, ids = fixture()
        modified = raw.replace(
            b"2026-11-16T12:00:00.123456789Z",
            b"2026-99-16T12:00:00.123456789Z",
        )
        with self.assertRaises(TrafficEvidenceError):
            self.run_capture(modified, ids)

    def test_reject_truncated_capture(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            self.run_capture(raw[:-1], ids)

    def test_reject_invalid_container_before_execution(self):
        with patch(
            "experiments.docker_envoy_capture_final.subprocess.Popen"
        ) as popen:
            with self.assertRaises(TrafficEvidenceError):
                capture_envoy_logs(
                    "production-envoy",
                    since=SINCE,
                    until=UNTIL,
                    expected_request_ids=["a"],
                )
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
