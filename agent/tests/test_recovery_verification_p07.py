"""Deterministic offline recovery verification tests."""

import unittest

from agent.recovery_verification import VerificationError, verify_recovery
from agent.signal_adapter import SignalValidationError


def signal(identifier, status, target="api"):
    return {
        "signal_id": identifier,
        "target": target,
        "status": status,
    }


class RecoveryVerificationTests(unittest.TestCase):

    def test_recovered(self):
        self.assertEqual(
            verify_recovery(signal("before", 503), signal("after", 200)),
            "SUCCESS",
        )

    def test_still_failing(self):
        self.assertEqual(
            verify_recovery(signal("before", 503), signal("after", 503)),
            "FAILED",
        )

    def test_ambiguous(self):
        self.assertEqual(
            verify_recovery(signal("before", 503), signal("after", 429)),
            "INCONCLUSIVE",
        )

    def test_healthy_baseline_cannot_claim_recovery(self):
        self.assertEqual(
            verify_recovery(signal("before", 200), signal("after", 200)),
            "INCONCLUSIVE",
        )

    def test_mismatched_targets_rejected(self):
        with self.assertRaises(VerificationError):
            verify_recovery(
                signal("before", 503, "api"),
                signal("after", 200, "auth"),
            )

    def test_same_observation_rejected(self):
        with self.assertRaises(VerificationError):
            verify_recovery(
                signal("same", 503),
                signal("same", 200),
            )

    def test_invalid_signal_rejected(self):
        with self.assertRaises(SignalValidationError):
            verify_recovery(
                signal("before", 503),
                {"signal_id": "after", "target": "api", "status": True},
            )

    def test_100_offline_scenarios(self):
        for index in range(100):
            before = signal("before-" + str(index), 503)
            status = 200 if index % 2 == 0 else 503
            after = signal("after-" + str(index), status)

            expected = "SUCCESS" if index % 2 == 0 else "FAILED"

            with self.subTest(index=index):
                self.assertEqual(verify_recovery(before, after), expected)


if __name__ == "__main__":
    unittest.main()
