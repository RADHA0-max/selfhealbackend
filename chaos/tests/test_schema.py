"""Offline validation tests for benchmark chaos scenarios."""

import copy
import unittest

from chaos.schema import (
    ChaosValidationError,
    load_catalog,
    validate_scenario,
)


class TestChaosSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_catalog_contains_ten_scenarios(self):
        self.assertEqual(len(self.catalog), 10)

    def test_all_scenarios_validate(self):
        for scenario in self.catalog.values():
            with self.subTest(scenario=scenario["id"]):
                result = validate_scenario(scenario, self.catalog)
                self.assertEqual(result.scenario_id, scenario["id"])

    def test_reject_unknown_scenario(self):
        with self.assertRaises(ChaosValidationError):
            validate_scenario({"id": "SHB-999"}, self.catalog)

    def test_reject_modified_target(self):
        scenario = copy.deepcopy(self.catalog["SHB-001"])
        scenario["target"] = "production"

        with self.assertRaises(ChaosValidationError):
            validate_scenario(scenario, self.catalog)

    def test_reject_modified_fault(self):
        scenario = copy.deepcopy(self.catalog["SHB-001"])
        scenario["fault"] = "stop"

        with self.assertRaises(ChaosValidationError):
            validate_scenario(scenario, self.catalog)

    def test_reject_extra_fields(self):
        scenario = copy.deepcopy(self.catalog["SHB-001"])
        scenario["command"] = "docker stop db"

        with self.assertRaises(ChaosValidationError):
            validate_scenario(scenario, self.catalog)

    def test_reject_modified_latency(self):
        scenario = copy.deepcopy(self.catalog["SHB-005"])
        scenario["delay_ms"] = 999999

        with self.assertRaises(ChaosValidationError):
            validate_scenario(scenario, self.catalog)

    def test_reject_missing_fields(self):
        scenario = copy.deepcopy(self.catalog["SHB-001"])
        del scenario["severity"]

        with self.assertRaises(ChaosValidationError):
            validate_scenario(scenario, self.catalog)

    def test_reject_non_object(self):
        with self.assertRaises(ChaosValidationError):
            validate_scenario("SHB-001", self.catalog)


if __name__ == "__main__":
    unittest.main()
