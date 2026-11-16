"""Offline sustained incident integration and fail-closed regression tests."""

import json
import unittest

from agent.offline_incident import evaluate_sustained_offline_incident
from agent.recovery_verification import (
    VerificationError,
    verify_sustained_recovery,
)
from agent.signal_adapter import SignalValidationError


def signal(identifier, status, target="api"):
    return {
        "signal_id": identifier,
        "target": target,
        "status": status,
    }


class FakeRPC:
    def __init__(self):
        self.calls = 0

    def call(self, *args, **kwargs):
        self.calls += 1
        return {
            "ok": True,
            "content": json.dumps({
                "category": "service_failure",
                "target": "api",
                "confidence": 0.8,
                "summary": "Synthetic offline diagnosis.",
                "recommended_action": "investigate_api",
            }),
        }


class SustainedIncidentIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.before = signal("before", 503)
        self.healthy = [
            signal("a", 200),
            signal("b", 200),
            signal("c", 200),
        ]

    def test_sustained_success_is_observational_only(self):
        rpc = FakeRPC()

        result = evaluate_sustained_offline_incident(
            rpc, self.before, self.healthy
        )

        self.assertEqual(result["observation_outcome"], "SUCCESS")
        self.assertEqual(result["observations_checked"], 3)
        self.assertEqual(rpc.calls, 1)
        self.assertFalse(result["mitigation_executed"])
        self.assertFalse(result["recovery_attributed_to_agent"])

    def test_regression_fails(self):
        rpc = FakeRPC()

        result = evaluate_sustained_offline_incident(
            rpc,
            self.before,
            [signal("a", 200), signal("b", 503), signal("c", 200)],
        )

        self.assertEqual(result["observation_outcome"], "FAILED")
        self.assertEqual(rpc.calls, 1)

    def test_incomplete_sequence_is_inconclusive(self):
        rpc = FakeRPC()

        result = evaluate_sustained_offline_incident(
            rpc, self.before, self.healthy[:2]
        )

        self.assertEqual(result["observation_outcome"], "INCONCLUSIVE")

    def test_invalid_later_observation_blocks_rpc(self):
        rpc = FakeRPC()
        observations = [
            signal("a", 503),
            {"signal_id": "b", "target": "api", "status": True},
        ]

        with self.assertRaises(SignalValidationError):
            evaluate_sustained_offline_incident(
                rpc, self.before, observations
            )

        self.assertEqual(rpc.calls, 0)

    def test_duplicate_after_failure_blocks_rpc(self):
        rpc = FakeRPC()

        with self.assertRaises(VerificationError):
            evaluate_sustained_offline_incident(
                rpc,
                self.before,
                [signal("a", 503), signal("a", 200)],
            )

        self.assertEqual(rpc.calls, 0)

    def test_late_target_mismatch_blocks_rpc(self):
        rpc = FakeRPC()

        with self.assertRaises(VerificationError):
            evaluate_sustained_offline_incident(
                rpc,
                self.before,
                [signal("a", 200), signal("b", 503, "auth")],
            )

        self.assertEqual(rpc.calls, 0)

    def test_too_many_observations_blocks_rpc(self):
        rpc = FakeRPC()
        observations = [
            signal("obs-%d" % index, 200)
            for index in range(11)
        ]

        with self.assertRaises(VerificationError):
            evaluate_sustained_offline_incident(
                rpc, self.before, observations
            )

        self.assertEqual(rpc.calls, 0)

    def test_late_invalid_input_always_rejected(self):
        for index in range(100):
            observations = [
                signal("a-%d" % index, 503),
                signal("b-%d" % index, 200),
                {"signal_id": "bad-%d" % index,
                 "target": "api", "status": True},
            ]

            with self.subTest(index=index):
                with self.assertRaises(SignalValidationError):
                    verify_sustained_recovery(
                        signal("before-%d" % index, 503),
                        observations,
                    )


if __name__ == "__main__":
    unittest.main()
