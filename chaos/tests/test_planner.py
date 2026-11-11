"""Offline safety tests for deterministic chaos planning."""

import json
import unittest

from chaos.planner import plan_scenario, plan_to_dict
from chaos.schema import ChaosValidationError


class TestChaosPlanner(unittest.TestCase):

    def test_dry_run_plan(self):
        plan = plan_scenario("SHB-001")

        self.assertEqual(plan.mode, "dry_run")
        self.assertFalse(plan.executable)
        self.assertEqual(plan.approval_status, "blocked")

    def test_all_scenarios_plan(self):
        for number in range(1, 11):
            scenario_id = f"SHB-{number:03d}"

            with self.subTest(scenario=scenario_id):
                plan = plan_scenario(scenario_id)
                self.assertEqual(plan.scenario_id, scenario_id)
                self.assertFalse(plan.executable)

    def test_latency_parameters(self):
        plan = plan_scenario("SHB-005")
        self.assertEqual(plan.parameters["delay_ms"], 2600)

    def test_healthy_scenario(self):
        plan = plan_scenario("SHB-010")

        self.assertEqual(plan.fault, "none")
        self.assertEqual(plan.target, "none")
        self.assertEqual(plan.parameters, {})

    def test_reject_live_mode(self):
        with self.assertRaises(ChaosValidationError):
            plan_scenario("SHB-001", mode="live")

    def test_reject_unknown_scenario(self):
        with self.assertRaises(ChaosValidationError):
            plan_scenario("SHB-999")

    def test_reject_non_string_id(self):
        with self.assertRaises(ChaosValidationError):
            plan_scenario(123)

    def test_deterministic_plan_id(self):
        first = plan_scenario("SHB-001")
        second = plan_scenario("SHB-001")

        self.assertEqual(first.plan_id, second.plan_id)

    def test_json_serializable(self):
        plan = plan_scenario("SHB-001")
        serialized = json.dumps(plan_to_dict(plan))

        self.assertIn('"executed": false', serialized)

    def test_audit_reports_no_execution(self):
        plan = plan_scenario("SHB-001")

        self.assertFalse(plan.audit["executed"])
        self.assertEqual(
            plan.audit["approval_status"],
            "blocked",
        )


if __name__ == "__main__":
    unittest.main()
