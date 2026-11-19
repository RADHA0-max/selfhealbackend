import json
import unittest

from experiments.envoy_reconciliation_final import reconcile_envoy_jsonl
from experiments.tests.test_envoy_evidence_final import sample
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def fixture():
    raw = sample()
    records = [json.loads(line) for line in raw.splitlines()]
    ids = [record["request_id"] for record in records]
    return raw, ids


class TestEnvoyReconciliationFinal(unittest.TestCase):

    def test_exact_manifest(self):
        raw, ids = fixture()
        result = reconcile_envoy_jsonl(raw, ids)
        self.assertTrue(result["request_ids_match"])
        self.assertEqual(result["observed_request_count"], len(ids))
        self.assertFalse(result["capture_completeness_verified"])

    def test_order_independent_manifest(self):
        raw, ids = fixture()
        result = reconcile_envoy_jsonl(raw, list(reversed(ids)))
        self.assertTrue(result["request_ids_match"])

    def test_missing_manifest_entry(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_jsonl(raw, ids[:-1])

    def test_unexpected_manifest_entry(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_jsonl(raw, ids + ["extra-request"])

    def test_duplicate_manifest_entry(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_jsonl(raw, ids + [ids[0]])

    def test_duplicate_observed_request(self):
        raw, ids = fixture()
        records = [json.loads(line) for line in raw.splitlines()]
        records[1]["request_id"] = records[0]["request_id"]
        modified = (
            "\n".join(json.dumps(record) for record in records) + "\n"
        ).encode()
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_jsonl(modified, ids)

    def test_reject_non_bytes(self):
        raw, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_jsonl(raw.decode(), ids)

    def test_reject_invalid_utf8(self):
        _, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_jsonl(b"\xff\n", ids)

    def test_reject_invalid_json(self):
        _, ids = fixture()
        with self.assertRaises(TrafficEvidenceError):
            reconcile_envoy_jsonl(b'{"broken":\n', ids)


if __name__ == "__main__":
    unittest.main()
