import unittest

from experiments.request_reconciliation_final import reconcile_request_ids
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class TestRequestReconciliationFinal(unittest.TestCase):

    def test_exact_match(self):
        result = reconcile_request_ids(
            ["run-1", "run-2", "run-3"],
            ["run-3", "run-1", "run-2"],
        )
        self.assertEqual(result["expected_request_count"], 3)
        self.assertTrue(result["request_ids_match"])
        self.assertFalse(result["capture_completeness_verified"])

    def test_manifest_hash_independent_of_order(self):
        a = reconcile_request_ids(["a", "b"], ["b", "a"])
        b = reconcile_request_ids(["b", "a"], ["a", "b"])
        self.assertEqual(
            a["request_manifest_sha256"],
            b["request_manifest_sha256"],
        )

    def test_missing_request(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(["a", "b"], ["a"])

    def test_unexpected_request(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(["a"], ["a", "b"])

    def test_duplicate_expected(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(["a", "a"], ["a"])

    def test_duplicate_observed(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(["a"], ["a", "a"])

    def test_invalid_request_id(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(["../bad/id"], ["../bad/id"])

    def test_reject_empty_manifest(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids([], [])

    def test_reject_oversized_manifest(self):
        ids = [f"req-{i}" for i in range(2001)]
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(ids, ids)

    def test_reject_non_list(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(("a",), ["a"])

    def test_reject_non_string(self):
        with self.assertRaises(TrafficEvidenceError):
            reconcile_request_ids(["a", 1], ["a", 1])


if __name__ == "__main__":
    unittest.main()
