"""Regression tests for bounded offline k6 manifest parsing."""

import json
import unittest

from experiments.reconcile_archived_run_final import parse_k6_stream
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def record(request_id):
    return {
        "type": "Point",
        "metric": "nanoclaw_request_manifest",
        "data": {
            "value": 1,
            "tags": {
                "workload": "organic_60vu",
                "request_id": request_id,
            },
        },
    }


def encode(*rows):
    return b"".join(
        json.dumps(row).encode() + b"\n"
        for row in rows
    )


class OfflineReconciliationTests(unittest.TestCase):

    def test_valid_manifest(self):
        self.assertEqual(
            parse_k6_stream(encode(record("a"), record("b"))),
            ["a", "b"],
        )

    def test_duplicate_id_rejected(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_stream(encode(record("a"), record("a")))

    def test_missing_id_rejected(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_stream(encode(record("a"), record(None)))

    def test_truncated_capture_rejected(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_stream(encode(record("a")).rstrip(b"\n"))

    def test_wrong_workload_rejected(self):
        row = record("a")
        row["data"]["tags"]["workload"] = "wrong"
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_stream(encode(row))

    def test_duplicate_json_key_rejected(self):
        raw = (
            b'{"type":"Point","type":"Point",'
            b'"metric":"nanoclaw_request_manifest",'
            b'"data":{"value":1,"tags":'
            b'{"workload":"organic_60vu","request_id":"a"}}}\n'
        )
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_stream(raw)


if __name__ == "__main__":
    unittest.main()
