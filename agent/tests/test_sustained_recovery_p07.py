"""Sustained recovery verification and adversarial sequence tests."""

import unittest

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


class SustainedRecoveryTests(unittest.TestCase):

    def test_three_healthy_observations(self):
        self.assertEqual(
            verify_sustained_recovery(
                signal("before", 503),
                [signal("a", 200), signal("b", 200), signal("c", 200)],
            ),
            "SUCCESS",
        )

    def test_one_healthy_observation_is_insufficient(self):
        self.assertEqual(
            verify_sustained_recovery(
                signal("before", 503),
                [signal("a", 200)],
            ),
            "INCONCLUSIVE",
        )

    def test_regression_fails(self):
        self.assertEqual(
            verify_sustained_recovery(
                signal("before", 503),
                [signal("a", 200), signal("b", 200), signal("c", 503)],
            ),
            "FAILED",
        )

    def test_ambiguous_status_is_inconclusive(self):
        self.assertEqual(
            verify_sustained_recovery(
                signal("before", 503),
                [signal("a", 200), signal("b", 429), signal("c", 200)],
            ),
            "INCONCLUSIVE",
        )

    def test_healthy_baseline_is_inconclusive(self):
        self.assertEqual(
            verify_sustained_recovery(
                signal("before", 200),
                [signal("a", 200), signal("b", 200), signal("c", 200)],
            ),
            "INCONCLUSIVE",
        )

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(VerificationError):
            verify_sustained_recovery(
                signal("before", 503),
                [signal("a", 200), signal("a", 200), signal("c", 200)],
            )

    def test_target_mismatch_rejected(self):
        with self.assertRaises(VerificationError):
            verify_sustained_recovery(
                signal("before", 503),
                [signal("a", 200, "auth")],
            )

    def test_invalid_observation_rejected(self):
        with self.assertRaises(SignalValidationError):
            verify_sustained_recovery(
                signal("before", 503),
                [{"signal_id": "a", "target": "api", "status": True}],
            )

    def test_invalid_threshold_rejected(self):
        for threshold in (True, 0, 1, 11, 2.5, "3"):
            with self.subTest(threshold=threshold):
                with self.assertRaises(VerificationError):
                    verify_sustained_recovery(
                        signal("before", 503), [], threshold
                    )

    def test_100_sustained_sequences(self):
        for index in range(100):
            statuses = [200, 200, 200] if index % 2 == 0 else [200, 503, 200]
            observations = [
                signal("after-%d-%d" % (index, step), status)
                for step, status in enumerate(statuses)
            ]

            expected = "SUCCESS" if index % 2 == 0 else "FAILED"

            with self.subTest(index=index):
                self.assertEqual(
                    verify_sustained_recovery(
                        signal("before-%d" % index, 503),
                        observations,
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
