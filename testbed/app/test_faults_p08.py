"""Offline testbed fault-controller tests."""

import os
import unittest
from unittest.mock import patch

from testbed.app.faults import (
    FaultConfigurationError,
    FaultController,
    controller_from_environment,
)


class FaultControllerTests(unittest.TestCase):

    def test_healthy_default(self):
        controller = FaultController()
        self.assertEqual(
            [controller.readiness_status() for _ in range(4)],
            [200, 200, 200, 200],
        )

    def test_outage(self):
        controller = FaultController("outage")
        self.assertEqual(
            [controller.readiness_status() for _ in range(4)],
            [503, 503, 503, 503],
        )

    def test_latency_status(self):
        controller = FaultController("latency")
        self.assertEqual(
            [controller.readiness_status() for _ in range(4)],
            [200, 200, 200, 200],
        )

    def test_timeout_response_status(self):
        controller = FaultController("timeout_response")
        self.assertEqual(
            [controller.readiness_status() for _ in range(4)],
            [504, 504, 504, 504],
        )

    def test_intermittent(self):
        controller = FaultController("intermittent")
        self.assertEqual(
            [controller.readiness_status() for _ in range(6)],
            [503, 200, 503, 200, 503, 200],
        )

    def test_invalid_mode_rejected(self):
        for mode in ("", "shell", None, True, "OUTAGE"):
            with self.subTest(mode=mode):
                with self.assertRaises(FaultConfigurationError):
                    FaultController(mode)

    def test_environment_selection(self):
        with patch.dict(
            os.environ,
            {"NANOCLAW_TESTBED_FAULT_MODE": "outage"},
        ):
            controller = controller_from_environment()
        self.assertEqual(controller.readiness_status(), 503)

    def test_invalid_environment_fails_closed(self):
        with patch.dict(
            os.environ,
            {"NANOCLAW_TESTBED_FAULT_MODE": "unknown"},
        ):
            with self.assertRaises(FaultConfigurationError):
                controller_from_environment()


if __name__ == "__main__":
    unittest.main()
