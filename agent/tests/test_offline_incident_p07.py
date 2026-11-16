"""Offline incident lifecycle integration and failure tests."""

import json
import unittest

from agent.offline_incident import evaluate_offline_incident
from agent.signal_adapter import SignalValidationError


def signal(identifier, status, target="api"):
    return {
        "signal_id": identifier,
        "target": target,
        "status": status,
    }


class FakeRPC:
    def __init__(self, category="service_failure"):
        self.category = category
        self.calls = 0

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


class OfflineIncidentTests(unittest.TestCase):

    def test_improved_observation(self):
        rpc = FakeRPC()
        result = evaluate_offline_incident(
            rpc, signal("before", 503), signal("after", 200)
        )

        self.assertEqual(result["observation_outcome"], "SUCCESS")
        self.assertFalse(result["mitigation_executed"])
        self.assertFalse(result["recovery_attributed_to_agent"])
        self.assertEqual(rpc.calls, 1)

    def test_persistent_failure(self):
        rpc = FakeRPC()
        result = evaluate_offline_incident(
            rpc, signal("before", 503), signal("after", 503)
        )
        self.assertEqual(result["observation_outcome"], "FAILED")

    def test_ambiguous_observation(self):
        rpc = FakeRPC()
        result = evaluate_offline_incident(
            rpc, signal("before", 503), signal("after", 429)
        )
        self.assertEqual(result["observation_outcome"], "INCONCLUSIVE")

    def test_unsupported_diagnosis_is_gated(self):
        rpc = FakeRPC("dependency_failure")
        result = evaluate_offline_incident(
            rpc, signal("before", 503), signal("after", 200)
        )
        self.assertEqual(result["diagnosis_category"], "unknown")
        self.assertEqual(
            result["diagnosis_action"], "collect_more_evidence"
        )

    def test_invalid_after_never_calls_model(self):
        rpc = FakeRPC()
        with self.assertRaises(SignalValidationError):
            evaluate_offline_incident(
                rpc,
                signal("before", 503),
                {"signal_id": "after", "target": "api", "status": True},
            )
        self.assertEqual(rpc.calls, 0)

    def test_mismatched_target_never_calls_model(self):
        rpc = FakeRPC()
        with self.assertRaises(ValueError):
            evaluate_offline_incident(
                rpc, signal("before", 503),
                signal("after", 200, "auth")
            )
        self.assertEqual(rpc.calls, 0)

    def test_duplicate_observation_never_calls_model(self):
        rpc = FakeRPC()
        with self.assertRaises(ValueError):
            evaluate_offline_incident(
                rpc, signal("same", 503), signal("same", 200)
            )
        self.assertEqual(rpc.calls, 0)

    def test_100_offline_incidents(self):
        rpc = FakeRPC()
        for index in range(100):
            before = signal("before-" + str(index), 503)
            after = signal(
                "after-" + str(index),
                200 if index % 2 == 0 else 503,
            )

            result = evaluate_offline_incident(rpc, before, after)
            expected = "SUCCESS" if index % 2 == 0 else "FAILED"

            with self.subTest(index=index):
                self.assertEqual(result["observation_outcome"], expected)
                self.assertFalse(result["mitigation_executed"])

        self.assertEqual(rpc.calls, 100)


if __name__ == "__main__":
    unittest.main()
