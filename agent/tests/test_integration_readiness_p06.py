"""Offline integration-readiness tests for the provisional signal API."""

import json
import unittest

from agent.signal_diagnosis import diagnose_signal
from agent.signal_adapter import SignalValidationError


def response(category, target, action):
    return json.dumps({
        "category": category,
        "target": target,
        "confidence": 0.8,
        "summary": "Synthetic diagnosis for offline testing.",
        "recommended_action": action,
    })


class FakeRPC:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def call(self, *args, **kwargs):
        self.calls += 1
        return {"ok": True, "content": self.content}


class IntegrationReadinessTests(unittest.TestCase):

    def test_invalid_signal_never_reaches_rpc(self):
        rpc = FakeRPC(
            response("unknown", "api", "collect_more_evidence")
        )

        with self.assertRaises(SignalValidationError):
            diagnose_signal(rpc, {
                "signal_id": "bad-001",
                "target": "api",
                "status": 503,
                "unexpected": "untrusted",
            })

        self.assertEqual(rpc.calls, 0)

    def test_unsupported_dependency_is_downgraded(self):
        rpc = FakeRPC(
            response("dependency_failure", "api", "investigate_api")
        )

        result = diagnose_signal(rpc, {
            "signal_id": "test-001",
            "target": "api",
            "status": 503,
        })

        self.assertEqual(result.category, "unknown")
        self.assertEqual(
            result.recommended_action,
            "collect_more_evidence",
        )
        self.assertEqual(rpc.calls, 1)

    def test_supported_latency_is_preserved(self):
        rpc = FakeRPC(
            response("latency", "worker", "investigate_latency")
        )

        result = diagnose_signal(rpc, {
            "signal_id": "test-002",
            "target": "worker",
            "status": 504,
            "latency_ms": 5000,
        })

        self.assertEqual(result.category, "latency")
        self.assertEqual(result.target, "worker")
        self.assertEqual(rpc.calls, 1)

    def test_mismatched_target_is_downgraded(self):
        rpc = FakeRPC(
            response("service_failure", "database", "investigate_database")
        )

        result = diagnose_signal(rpc, {
            "signal_id": "test-003",
            "target": "api",
            "status": 503,
        })

        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.target, "api")
        self.assertEqual(rpc.calls, 1)


if __name__ == "__main__":
    unittest.main()
