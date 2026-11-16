"""Offline deterministic fault-sequence and latency tests."""

import unittest

from testbed.app.faults import (
    LATENCY_SECONDS,
    FaultController,
    FaultObservation,
)


class FaultSequenceTests(unittest.TestCase):

    def test_measured_latency_configuration(self):
        observation = FaultController("latency").next_observation()
        self.assertEqual(observation.status, 200)
        self.assertEqual(observation.delay_seconds, LATENCY_SECONDS)
        self.assertGreater(observation.delay_seconds, 0)
        self.assertLessEqual(observation.delay_seconds, 1)

    def test_timeout_response_is_not_latency(self):
        observation = FaultController("timeout_response").next_observation()
        self.assertEqual(observation, FaultObservation(504, 0.0))

    def test_recovering_sequence(self):
        controller = FaultController("recovering")
        statuses = [
            controller.next_observation().status
            for _ in range(8)
        ]
        self.assertEqual(
            statuses,
            [503, 503, 503, 200, 200, 200, 200, 200],
        )

    def test_regression_sequence(self):
        controller = FaultController("regression")
        statuses = [
            controller.next_observation().status
            for _ in range(9)
        ]
        self.assertEqual(
            statuses,
            [503, 503, 503, 200, 200, 200, 503, 503, 503],
        )

    def test_liveness_unaffected_by_fault_controller(self):
        self.assertEqual(
            FaultController("outage").next_observation().status,
            503,
        )
        # /health is handled independently of FaultController
        # in testbed/app/server.py.

    def test_invalid_modes_rejected(self):
        for mode in ("reboot", "shell", "production", "", None):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    FaultController(mode)


if __name__ == "__main__":
    unittest.main()
