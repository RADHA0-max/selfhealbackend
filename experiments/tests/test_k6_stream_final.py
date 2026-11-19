import json
import tempfile
import unittest
from pathlib import Path

from experiments.k6_stream_final import extract_k6_manifest
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def point(request_id):
    return {
        "type": "Point",
        "metric": "nanoclaw_request_manifest",
        "data": {
            "value": 1,
            "tags": {
                "request_id": request_id,
                "workload": "organic_60vu",
            },
        },
    }


def encode(records):
    return (
        "\n".join(json.dumps(record) for record in records) + "\n"
    ).encode()


class TestK6StreamFinal(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "k6-full.jsonl"

    def write(self, records):
        self.path.write_bytes(encode(records))

    def test_extract_with_unrelated_metrics(self):
        self.write([
            {"type": "Metric", "metric": "http_req_duration", "data": {}},
            point("req-1"),
            {"type": "Point", "metric": "http_reqs", "data": {"value": 1}},
            point("req-2"),
        ])
        result = extract_k6_manifest(str(self.path))
        self.assertEqual(result["request_ids"], ["req-1", "req-2"])
        self.assertEqual(result["request_count"], 2)
        self.assertFalse(result["capture_complete_verified"])

    def test_duplicate_ids(self):
        self.write([point("req-1"), point("req-1")])
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(str(self.path))

    def test_no_manifest(self):
        self.write([{"type": "Metric", "metric": "http_reqs", "data": {}}])
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(str(self.path))

    def test_invalid_json(self):
        self.path.write_bytes(b"{broken\n")
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(str(self.path))

    def test_unterminated_line(self):
        self.path.write_bytes(encode([point("req-1")]).rstrip(b"\n"))
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(str(self.path))

    def test_oversized_line(self):
        self.path.write_bytes(b"x" * 65537 + b"\n")
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(str(self.path))

    def test_symlink(self):
        self.write([point("req-1")])
        link = Path(self.tmp.name) / "link"
        link.symlink_to(self.path)
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(str(link))

    def test_directory(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(self.tmp.name)

    def test_missing_file(self):
        with self.assertRaises(TrafficEvidenceError):
            extract_k6_manifest(str(self.path))

    def test_invalid_path(self):
        for value in (None, "", 123, "bad\x00path"):
            with self.subTest(value=value):
                with self.assertRaises(TrafficEvidenceError):
                    extract_k6_manifest(value)


if __name__ == "__main__":
    unittest.main()
