"""Offline tests for the strict P07 diagnosis boundary."""

import json
import unittest

from agent.evidence_boundary import (
    EvidenceBoundaryError,
    diagnose_evidence,
)


class FakeRPC:
    def __init__(self, category="dependency_failure"):
        self.calls = 0
        self.category = category

    def call(self, *args, **kwargs):
        self.calls += 1
        return {
            "ok": True,
            "content": json.dumps({
                "category": self.category,
                "target": "api",
                "confidence": 0.8,
                "summary": "Synthetic offline diagnosis.",
                "recommended_action": "investigate_api",
            }),
        }


class EvidenceBoundaryTests(unittest.TestCase):

    def setUp(self):
        self.evidence = {
            "signal_id": "p07-001",
            "probes": {"api": {"status": 503}},
        }

    def test_valid_evidence_reaches_rpc_once(self):
        rpc = FakeRPC()
        result = diagnose_evidence(rpc, self.evidence)
        self.assertEqual(rpc.calls, 1)
        self.assertEqual(result.category, "unknown")

    def test_supported_failure_is_preserved(self):
        rpc = FakeRPC("service_failure")
        result = diagnose_evidence(rpc, self.evidence)
        self.assertEqual(result.category, "service_failure")

    def test_invalid_evidence_never_reaches_rpc(self):
        invalid = [
            None,
            {},
            {"signal_id": "x", "probes": {}},
            {"signal_id": "x", "probes": {"api": {"status": True}}},
            {"signal_id": "x", "probes": {"api": {"status": 503, "extra": 1}}},
            {"signal_id": "x", "probes": {"api": {"status": 503}}, "extra": 1},
            {"signal_id": "x", "probes": {"api": {"status": 503}, "auth": {"status": 503}}},
            {"signal_id": "x", "probes": {"api": {"status": 503.0}}},
            {"signal_id": "x", "probes": {"api": {"status": 503, "latency_ms": -1}}},
            {"signal_id": "x", "probes": {"api": {"status": 503}}, "bad": float("nan")},
        ]

        rpc = FakeRPC()
        for item in invalid:
            with self.subTest(item=str(item)):
                with self.assertRaises(EvidenceBoundaryError):
                    diagnose_evidence(rpc, item)

        self.assertEqual(rpc.calls, 0)

    def test_oversized_evidence_rejected(self):
        rpc = FakeRPC()
        evidence = dict(self.evidence)
        evidence["padding"] = "x" * 20000

        with self.assertRaises(EvidenceBoundaryError):
            diagnose_evidence(rpc, evidence)

        self.assertEqual(rpc.calls, 0)


if __name__ == "__main__":
    unittest.main()
