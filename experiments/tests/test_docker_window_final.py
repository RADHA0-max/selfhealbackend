import unittest
from unittest.mock import patch

from experiments.docker_envoy_capture_final import (
    _validate_window,
    capture_envoy_logs,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class TestDockerWindowFinal(unittest.TestCase):

    def test_valid_window(self):
        self.assertEqual(
            _validate_window(
                "2026-11-16T12:00:00Z",
                "2026-11-16T12:05:00Z",
            ),
            (
                "2026-11-16T12:00:00Z",
                "2026-11-16T12:05:00Z",
            ),
        )

    def test_reject_reverse_window(self):
        with self.assertRaises(TrafficEvidenceError):
            _validate_window(
                "2026-11-16T12:05:00Z",
                "2026-11-16T12:00:00Z",
            )

    def test_reject_long_window(self):
        with self.assertRaises(TrafficEvidenceError):
            _validate_window(
                "2026-11-16T12:00:00Z",
                "2026-11-16T12:11:00Z",
            )

    def test_reject_non_utc(self):
        with self.assertRaises(TrafficEvidenceError):
            _validate_window(
                "2026-11-16T12:00:00+05:30",
                "2026-11-16T12:01:00+05:30",
            )

    def test_reject_invalid_timestamp(self):
        with self.assertRaises(TrafficEvidenceError):
            _validate_window("invalid", "2026-11-16T12:01:00Z")

    def test_reject_missing_window_before_docker(self):
        with patch(
            "experiments.docker_envoy_capture_final.subprocess.Popen"
        ) as popen:
            with self.assertRaises(TrafficEvidenceError):
                capture_envoy_logs(
                    "nanoclaw-envoy",
                    since="invalid",
                    until="2026-11-16T12:01:00Z",
                )
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
