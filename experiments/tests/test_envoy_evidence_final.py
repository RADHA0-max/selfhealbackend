"""Offline security and integrity tests for Envoy evidence analysis."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments.envoy_evidence_final import analyze_envoy_evidence
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def sample():
    rows = []

    for index in range(3):
        rows.append({
            "timestamp": f"2026-11-16T12:00:0{index}Z",
            "client_ip": "172.20.0.5",
            "method": "GET",
            "path": "/ready",
            "status": "200",
            "duration_ms": "5",
            "user_agent": "NanoClaw-Test",
            "request_id": f"request-{index}",
        })

    return b"\n".join(
        json.dumps(row).encode("utf-8") for row in rows
    ) + b"\n"


class TestEnvoyEvidenceFinal(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "envoy.jsonl"
        self.path.write_bytes(sample())

    def test_valid_evidence(self):
        result = analyze_envoy_evidence(self.path)
        self.assertEqual(result["validated_event_count"], 3)
        self.assertEqual(result["summary"]["request_count"], 3)

    def test_sha256_integrity(self):
        import hashlib
        result = analyze_envoy_evidence(self.path)
        self.assertEqual(
            result["evidence_sha256"],
            hashlib.sha256(sample()).hexdigest(),
        )

    def test_no_production_claims(self):
        result = analyze_envoy_evidence(self.path)
        self.assertFalse(result["mitigation_executed"])
        self.assertFalse(result["production_traffic_verified"])
        self.assertFalse(result["detector_classification_verified"])
        self.assertFalse(result["source_ip_separation_verified"])

    def test_reject_non_json(self):
        self.path.write_bytes(b"Envoy starting\n" + sample())
        with self.assertRaises(TrafficEvidenceError):
            analyze_envoy_evidence(self.path)

    def test_reject_duplicate_json_keys(self):
        self.path.write_bytes(
            sample().replace(
                b'"status": "200"',
                b'"status": "200", "status": "503"',
                1,
            )
        )
        with self.assertRaises(TrafficEvidenceError):
            analyze_envoy_evidence(self.path)

    def test_reject_symlink(self):
        link = Path(self.temp.name) / "linked.jsonl"
        link.symlink_to(self.path)
        with self.assertRaises(TrafficEvidenceError):
            analyze_envoy_evidence(link)

    def test_reject_empty_file(self):
        self.path.write_bytes(b"")
        with self.assertRaises(TrafficEvidenceError):
            analyze_envoy_evidence(self.path)

    def test_reject_oversized_file(self):
        self.path.write_bytes(b"x" * 512_001)
        with self.assertRaises(TrafficEvidenceError):
            analyze_envoy_evidence(self.path)

    def test_reject_invalid_ip(self):
        self.path.write_bytes(
            sample().replace(b"172.20.0.5", b"not-an-ip")
        )
        with self.assertRaises(TrafficEvidenceError):
            analyze_envoy_evidence(self.path)


if __name__ == "__main__":
    unittest.main()
