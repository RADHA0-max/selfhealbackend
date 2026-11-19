import json
import unittest

from experiments.k6_manifest_final import parse_k6_manifest
from experiments.request_reconciliation_final import reconcile_request_ids
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
    return ("\n".join(json.dumps(x) for x in records) + "\n").encode()


class TestK6ManifestFinal(unittest.TestCase):

    def test_valid_manifest(self):
        ids = parse_k6_manifest(encode([point("a"), point("b")]))
        self.assertEqual(ids, ["a", "b"])

    def test_reconcile(self):
        ids = parse_k6_manifest(encode([point("a"), point("b")]))
        result = reconcile_request_ids(ids, ["b", "a"])
        self.assertTrue(result["request_ids_match"])

    def test_duplicate(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_manifest(encode([point("a"), point("a")]))

    def test_invalid_id(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_manifest(encode([point("../bad")]))

    def test_wrong_workload(self):
        record = point("a")
        record["data"]["tags"]["workload"] = "unknown"
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_manifest(encode([record]))

    def test_invalid_value(self):
        record = point("a")
        record["data"]["value"] = 2
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_manifest(encode([record]))

    def test_invalid_json(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_manifest(b"{broken\n")

    def test_empty(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_manifest(b"")

    def test_oversized(self):
        with self.assertRaises(TrafficEvidenceError):
            parse_k6_manifest(b"x" * (2 * 1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()
