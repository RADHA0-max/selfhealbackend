import importlib.util
import unittest
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "measure_p01.py"
)

spec = importlib.util.spec_from_file_location("measure_p01", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def event(run_id, request_id, workload="p01_ddos"):
    return {
        "run_id": run_id,
        "request_id": request_id,
        "workload": workload,
    }


class MeasurementTests(unittest.TestCase):

    def test_exact_reconciliation_passes(self):
        expected = [
            event("arm-a", "a-1"),
            event("arm-b", "b-1"),
        ]

        result = module.measure(expected, list(expected))

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["matched_events"], 2)

    def test_missing_request_fails(self):
        result = module.measure(
            [event("arm-a", "a-1")],
            [],
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(result["missing"]), 1)

    def test_unexpected_request_fails(self):
        result = module.measure(
            [],
            [event("arm-a", "a-1")],
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(result["unexpected"]), 1)

    def test_duplicate_observation_fails(self):
        item = event("arm-a", "a-1")

        result = module.measure([item], [item, item])

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["duplicate_observed_ids"], ["a-1"])

    def test_cross_arm_collision_fails(self):
        result = module.measure(
            [event("arm-a", "shared")],
            [event("arm-b", "shared")],
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["cross_arm_collisions"], ["shared"])

    def test_workload_mismatch_fails(self):
        result = module.measure(
            [event("arm-a", "a-1", "p01_ddos")],
            [event("arm-a", "a-1", "p01_scraper")],
        )

        self.assertEqual(result["status"], "FAIL")

    def test_invalid_event_rejected(self):
        with self.assertRaises(ValueError):
            module.measure(
                [{"run_id": "arm-a", "request_id": "a-1"}],
                [],
            )


if __name__ == "__main__":
    unittest.main()
