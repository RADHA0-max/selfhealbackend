"""Integration tests for synthetic-signal diagnosis gating."""

import unittest

from agent.signal_diagnosis import diagnose_signal


class FakeRPC:
    def __init__(self, category, target="api"):
        self.category = category
        self.target = target
        self.calls = 0

    def call(self, model, messages, **kwargs):
        self.calls += 1
        return {
            "ok": True,
            "content": (
                '{"category":"' + self.category + '",'
                '"target":"' + self.target + '",'
                '"confidence":0.9,'
                '"summary":"Model diagnosis",'
                '"recommended_action":"investigate_api"}'
            ),
        }


class SignalEvidenceGateTests(unittest.TestCase):
    def test_unsupported_dependency_is_downgraded(self):
        rpc = FakeRPC("dependency_failure")
        signal = {"signal_id": "gate-001", "target": "api", "status": 503}

        result = diagnose_signal(rpc, signal)

        self.assertEqual(rpc.calls, 1)
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.target, "api")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.recommended_action, "collect_more_evidence")

    def test_supported_service_failure_is_preserved(self):
        rpc = FakeRPC("service_failure")
        signal = {"signal_id": "gate-002", "target": "api", "status": 503}

        result = diagnose_signal(rpc, signal)

        self.assertEqual(rpc.calls, 1)
        self.assertEqual(result.category, "service_failure")
        self.assertEqual(result.recommended_action, "investigate_api")


if __name__ == "__main__":
    unittest.main()
