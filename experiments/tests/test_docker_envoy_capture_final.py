import unittest
from unittest.mock import patch

from experiments.docker_envoy_capture_final import (
    capture_envoy_logs,
    normalize_docker_timestamps,
)
from experiments.tests.test_envoy_evidence_final import sample
from experiments.traffic_evidence_p15 import TrafficEvidenceError

PREFIX = b"2026-11-16T12:00:00.123456789Z "


def stamped(raw):
    return b"".join(PREFIX + line + b"\n" for line in raw.splitlines())


class TestDockerEnvoyCaptureFinal(unittest.TestCase):

    def test_normalize_timestamped_jsonl(self):
        self.assertEqual(normalize_docker_timestamps(stamped(sample())), sample())

    def test_reject_unstamped_capture(self):
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(sample())

    def test_reject_truncated_capture(self):
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(stamped(sample())[:-1])

    def test_reject_mixed_timestamp_formats(self):
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(stamped(sample()) + b"startup\n")

    def test_reject_oversized_capture(self):
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(b"x" * 1_000_001)

    def test_reject_invalid_container_name_before_execution(self):
        with patch(
            "experiments.docker_envoy_capture_final.subprocess.Popen"
        ) as popen:
            with self.assertRaises(TrafficEvidenceError):
                capture_envoy_logs("../../../etc/passwd", since="2026-11-16T12:00:00Z", until="2026-11-16T12:01:00Z")
            popen.assert_not_called()

    def test_reject_empty_container_name(self):
        with patch(
            "experiments.docker_envoy_capture_final.subprocess.Popen"
        ) as popen:
            with self.assertRaises(TrafficEvidenceError):
                capture_envoy_logs("", since="2026-11-16T12:00:00Z", until="2026-11-16T12:01:00Z")
            popen.assert_not_called()

    def test_reject_wrong_container_prefix(self):
        with patch(
            "experiments.docker_envoy_capture_final.subprocess.Popen"
        ) as popen:
            with self.assertRaises(TrafficEvidenceError):
                capture_envoy_logs("production-envoy", since="2026-11-16T12:00:00Z", until="2026-11-16T12:01:00Z")
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
