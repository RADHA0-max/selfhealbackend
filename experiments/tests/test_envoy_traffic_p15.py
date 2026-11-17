"""Offline tests for bounded P15 Envoy access-log measurements."""

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from experiments.envoy_traffic_p15 import (
    parse_envoy_jsonl,
    summarize_envoy_file,
    summarize_envoy_jsonl,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def rows(count=20, gap_ms=100):
    start = dt.datetime(
        2026, 1, 1, tzinfo=dt.timezone.utc
    )

    return [
        {
            "timestamp": (
                start + dt.timedelta(milliseconds=i * gap_ms)
            ).isoformat(),
            "client_ip": "192.0.2.10",
            "method": "GET",
            "path": "/api/data" if i % 2 else "/health",
            "status": "200",
            "duration_ms": "12",
            "user_agent": "NanoClaw-Offline-Fixture/1.0",
            "request_id": f"req-{i}",
        }
        for i in range(count)
    ]


def encode(records):
    return (
        "\n".join(
            json.dumps(row, separators=(",", ":"))
            for row in records
        ) + "\n"
    ).encode("utf-8")


class TestEnvoyTrafficP15(unittest.TestCase):

    def setUp(self):
        self.records = rows()

    def reject(self, records):
        with self.assertRaises(TrafficEvidenceError):
            parse_envoy_jsonl(encode(records))

    def test_metrics(self):
        summary = summarize_envoy_jsonl(encode(self.records))
        self.assertEqual(summary["request_count"], 20)
        self.assertEqual(summary["unique_observed_ip_values"], 1)
        self.assertEqual(summary["path_counts"]["/health"], 10)
        self.assertFalse(summary["source_ip_separation_verified"])

    def test_rate_changes(self):
        slow = summarize_envoy_jsonl(encode(rows(20, 1000)))
        fast = summarize_envoy_jsonl(encode(rows(20, 50)))
        self.assertGreater(
            fast["requests_per_second"],
            slow["requests_per_second"] * 10,
        )

    def test_string_numbers(self):
        self.assertEqual(
            parse_envoy_jsonl(encode(self.records))[0]["status"],
            200,
        )

    def test_reject_unknown_field(self):
        records = copy.deepcopy(self.records)
        records[0]["trusted"] = True
        self.reject(records)

    def test_reject_bad_ip(self):
        records = copy.deepcopy(self.records)
        records[0]["client_ip"] = "not-an-ip"
        self.reject(records)

    def test_reject_out_of_order(self):
        records = copy.deepcopy(self.records)
        records[2]["timestamp"] = records[0]["timestamp"]
        self.reject(records)

    def test_reject_invalid_method(self):
        records = copy.deepcopy(self.records)
        records[0]["method"] = "POST"
        self.reject(records)

    def test_reject_unexpected_path(self):
        records = copy.deepcopy(self.records)
        records[0]["path"] = "/admin"
        self.reject(records)

    def test_reject_boolean_status(self):
        records = copy.deepcopy(self.records)
        records[0]["status"] = True
        self.reject(records)

    def test_reject_oversized_log(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_envoy_jsonl(b"x" * 512001)

    def test_reject_duplicate_json_keys(self):
        raw = encode(self.records)
        raw = raw.replace(
            b'"status":"200"',
            b'"status":"200","status":"503"',
            1,
        )
        with self.assertRaises(TrafficEvidenceError):
            parse_envoy_jsonl(raw)

    def test_equal_timestamps_allowed(self):
        records = copy.deepcopy(self.records)
        records[1]["timestamp"] = records[0]["timestamp"]
        parsed = parse_envoy_jsonl(encode(records))
        self.assertEqual(len(parsed), 20)

    def test_decreasing_timestamp_rejected(self):
        records = copy.deepcopy(self.records)
        records[2]["timestamp"] = records[0]["timestamp"]
        self.reject(records)

    def test_reject_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TrafficEvidenceError):
                summarize_envoy_file(directory)

    def test_reject_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.jsonl"
            path.write_bytes(b"")
            with self.assertRaises(TrafficEvidenceError):
                summarize_envoy_file(path)

    def test_reject_oversized_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.jsonl"
            path.write_bytes(b"x" * 512001)
            with self.assertRaises(TrafficEvidenceError):
                summarize_envoy_file(path)

    def test_reject_null_byte(self):
        records = copy.deepcopy(self.records)
        records[0]["user_agent"] = "agent" + chr(0) + "malicious"
        self.reject(records)

    def test_reject_nonfinite_duration(self):
        records = copy.deepcopy(self.records)
        records[0]["duration_ms"] = float("nan")
        self.reject(records)

    def test_reject_unauthorized_path(self):
        records = copy.deepcopy(self.records)
        records[0]["path"] = "/admin/config"
        self.reject(records)

    def test_reject_invalid_request_id(self):
        records = copy.deepcopy(self.records)
        records[0]["request_id"] = "../../etc/passwd"
        self.reject(records)

    def test_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "envoy.jsonl"
            path.write_bytes(encode(self.records))
            result = summarize_envoy_file(path)
            self.assertEqual(result["request_count"], 20)

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "real.jsonl"
            link = Path(directory) / "link.jsonl"
            target.write_bytes(encode(self.records))
            link.symlink_to(target)
            with self.assertRaises(TrafficEvidenceError):
                summarize_envoy_file(link)


if __name__ == "__main__":
    unittest.main()
