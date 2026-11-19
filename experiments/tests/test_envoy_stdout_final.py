import json
import unittest

from experiments.envoy_stdout_final import extract_envoy_stdout
from experiments.tests.test_envoy_evidence_final import sample
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class TestEnvoyStdoutFinal(unittest.TestCase):

    def test_mixed_stdout(self):
        raw = b"Envoy starting\n" + sample() + b"Envoy ready\n"
        report = extract_envoy_stdout(raw, capture_complete=True)
        self.assertEqual(report["validated_event_count"], 3)
        self.assertEqual(report["ignored_non_json_messages"], 2)
        self.assertEqual(report["summary"]["request_count"], 3)

    def test_reject_unverified_completeness(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(sample())

    def test_reject_false_completeness(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(sample(), capture_complete=False)

    def test_reject_truncated_line(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(sample()[:-1], capture_complete=True)

    def test_reject_malformed_json(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(
                sample() + b'{"timestamp":\n',
                capture_complete=True,
            )

    def test_reject_duplicate_json_keys(self):
        raw = sample().replace(
            b'"status": "200"',
            b'"status": "200", "status": "503"',
            1,
        )
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(raw, capture_complete=True)

    def test_reject_unknown_json_schema(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(
                sample() + b'{"event":"startup"}\n',
                capture_complete=True,
            )

    def test_reject_nonfinite_json(self):
        raw = sample().replace(
            b'"duration_ms": "5"',
            b'"duration_ms": NaN',
            1,
        )
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(raw, capture_complete=True)

    def test_reject_oversized_capture(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(
                b"x" * 1_000_001,
                capture_complete=True,
            )

    def test_reject_too_many_records(self):
        rows = sample().splitlines()
        raw = b"\n".join(rows * 667) + b"\n"
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(raw, capture_complete=True)

    def test_concurrent_start_timestamps_allowed(self):
        rows = sample().splitlines()
        raw = b"\n".join(reversed(rows)) + b"\n"
        result = extract_envoy_stdout(raw, capture_complete=True)
        self.assertIsNotNone(result)

    def test_reject_invalid_ip(self):
        raw = sample().replace(b"172.20.0.5", b"invalid-ip")
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(raw, capture_complete=True)

    def test_reject_empty_line(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(
                sample() + b"\n",
                capture_complete=True,
            )

    def test_reject_single_record(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_envoy_stdout(
                sample().splitlines()[0] + b"\n",
                capture_complete=True,
            )

    def test_no_unverified_claims(self):
        report = extract_envoy_stdout(
            sample(),
            capture_complete=True,
        )
        self.assertFalse(report["runtime_origin_verified"])
        self.assertFalse(report["production_traffic_verified"])
        self.assertFalse(report["source_ip_separation_verified"])
        self.assertFalse(report["detector_classification_verified"])
        self.assertFalse(report["mitigation_executed"])


if __name__ == "__main__":
    unittest.main()
