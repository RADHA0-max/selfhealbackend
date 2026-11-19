import unittest

from experiments.docker_envoy_capture_final import normalize_docker_timestamps
from experiments.tests.test_docker_envoy_capture_final import stamped
from experiments.tests.test_envoy_evidence_final import sample
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class TestDockerWindowEnforcementFinal(unittest.TestCase):

    def test_valid_timestamp_window(self):
        raw = stamped(sample())
        self.assertEqual(
            normalize_docker_timestamps(
                raw,
                since="2026-11-16T11:59:00Z",
                until="2026-11-16T12:01:00Z",
            ),
            sample(),
        )

    def test_reject_record_before_window(self):
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(
                stamped(sample()),
                since="2026-11-16T12:01:00Z",
                until="2026-11-16T12:02:00Z",
            )

    def test_reject_record_after_window(self):
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(
                stamped(sample()),
                since="2026-11-16T11:57:00Z",
                until="2026-11-16T11:59:00Z",
            )

    def test_reject_partial_window(self):
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(
                stamped(sample()),
                since="2026-11-16T11:59:00Z",
            )

    def test_reject_invalid_calendar_timestamp(self):
        raw = stamped(sample()).replace(
            b"2026-11-16T12:00:00.123456789Z",
            b"2026-99-16T12:00:00.123456789Z",
        )
        with self.assertRaises(TrafficEvidenceError):
            normalize_docker_timestamps(raw)


if __name__ == "__main__":
    unittest.main()
