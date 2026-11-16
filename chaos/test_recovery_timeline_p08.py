"""Deterministic chaos timeline and regression tests."""

import unittest

from chaos.recovery_timeline import (
    TimelineError,
    evaluate_timeline,
    validate_timeline,
)


def event(time_ms, status, latency=100, target="api"):
    return {
        "time_ms": time_ms,
        "target": target,
        "status": status,
        "latency_ms": latency,
    }


class RecoveryTimelineTests(unittest.TestCase):

    def test_sustained_recovery(self):
        result = evaluate_timeline([
            event(0, 503),
            event(1000, 200),
            event(2000, 200),
            event(3000, 200),
        ])
        self.assertEqual(result["observation_outcome"], "SUCCESS")
        self.assertEqual(result["first_sustained_recovery_ms"], 3000)
        self.assertFalse(result["recovery_attributed_to_agent"])

    def test_regression_after_recovery(self):
        result = evaluate_timeline([
            event(0, 503),
            event(1000, 200),
            event(2000, 200),
            event(3000, 200),
            event(4000, 503),
        ])
        self.assertEqual(result["observation_outcome"], "FAILED")
        self.assertEqual(result["regression_count"], 1)

    def test_recovery_after_regression(self):
        result = evaluate_timeline([
            event(0, 503),
            event(1000, 200),
            event(2000, 503),
            event(3000, 200),
            event(4000, 200),
            event(5000, 200),
        ])
        self.assertEqual(result["observation_outcome"], "SUCCESS")
        self.assertEqual(result["regression_count"], 1)

    def test_latency_failure(self):
        result = evaluate_timeline([
            event(0, 503),
            event(1000, 200, 5000),
            event(2000, 200, 5000),
            event(3000, 200, 5000),
        ])
        self.assertEqual(result["observation_outcome"], "FAILED")

    def test_healthy_baseline_is_inconclusive(self):
        result = evaluate_timeline([
            event(0, 200),
            event(1000, 200),
            event(2000, 200),
            event(3000, 200),
        ])
        self.assertEqual(result["observation_outcome"], "INCONCLUSIVE")

    def test_duplicate_timestamp_rejected(self):
        with self.assertRaises(TimelineError):
            validate_timeline([event(0, 503), event(0, 200)])

    def test_mixed_targets_rejected(self):
        with self.assertRaises(TimelineError):
            validate_timeline([
                event(0, 503),
                event(1000, 200, target="auth"),
            ])

    def test_boolean_status_rejected(self):
        with self.assertRaises(TimelineError):
            validate_timeline([
                event(0, 503),
                event(1000, True),
            ])

    def test_unexpected_fields_rejected(self):
        bad = event(1000, 200)
        bad["command"] = "shutdown"

        with self.assertRaises(TimelineError):
            validate_timeline([event(0, 503), bad])

    def test_bounded_long_timeline(self):
        events = [
            event(index * 100, 503 if index < 500 else 200)
            for index in range(1000)
        ]
        result = evaluate_timeline(events)
        self.assertEqual(result["observation_count"], 1000)
        self.assertEqual(result["observation_outcome"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
