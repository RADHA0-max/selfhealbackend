import copy
import unittest

from selfhealbench.bench.network_safety import review


def inventory():
    return {
        "complete": {k: True for k in ("host", "routes", "rules", "docker", "vpn")},
        "host_cidrs": ["172.16.40.0/22"], "route_cidrs": ["10.250.10.0/26"],
        "docker_cidrs": ["10.250.20.0/26"], "vpn_cidrs": [],
        "institutional_cidrs": [],
        "campus_allocation": {"confirmed": True, "candidate": "10.250.30.0/26",
                              "authority": "TEST ONLY: fictitious allocation"},
    }


class NetworkSafetyTests(unittest.TestCase):
    def test_host_overlap(self):
        value = inventory(); value["host_cidrs"].append("10.250.30.0/24")
        self.assertEqual(review("10.250.30.0/26", value)["status"], "rejected")

    def test_docker_overlap(self):
        value = inventory(); value["docker_cidrs"].append("10.250.30.0/26")
        self.assertEqual(review("10.250.30.0/26", value)["status"], "rejected")

    def test_vpn_overlap(self):
        value = inventory(); value["vpn_cidrs"].append("10.250.0.0/16")
        self.assertEqual(review("10.250.30.0/26", value)["status"], "rejected")

    def test_outside_permitted_space(self):
        for candidate in ("172.31.0.0/26", "192.168.2.0/26", "11.0.0.0/26", "::/26"):
            self.assertEqual(review(candidate, inventory())["status"], "rejected")

    def test_invalid_and_misaligned_cidr(self):
        for candidate in ("invalid", "10.250.30.1/26"):
            self.assertEqual(review(candidate, inventory())["status"], "rejected")

    def test_inappropriate_capacity(self):
        for candidate in ("10.250.30.0/27", "10.250.30.0/25"):
            self.assertEqual(review(candidate, inventory())["status"], "rejected")

    def test_missing_route_inventory_blocks(self):
        value = inventory(); value["complete"]["routes"] = False
        self.assertEqual(review("10.250.30.0/26", value)["status"], "blocked")

    def test_missing_campus_confirmation_blocks(self):
        value = inventory(); value["campus_allocation"]["confirmed"] = False
        self.assertEqual(review("10.250.30.0/26", value)["status"], "blocked")

    def test_complete_candidate_only_eligible_for_review(self):
        result = review("10.250.30.0/26", inventory(), "10.250.30.1")
        self.assertEqual(result["status"], "eligible_for_operator_review")
        self.assertEqual(result["conventional_usable_addresses"], 62)
        self.assertEqual(result["container_capacity_after_gateway"], 61)

    def test_network_creation_never_authorized(self):
        result = review("10.250.30.0/26", inventory())
        self.assertFalse(result["provisioning_allowed"])
        self.assertTrue(result["operator_network_approval_required"])

    def test_alternate_table_and_institutional_ranges(self):
        for field in ("route_cidrs", "institutional_cidrs"):
            value = inventory(); value[field].append("10.0.0.0/8")
            self.assertEqual(review("10.250.30.0/26", value)["status"], "rejected")

    def test_bad_gateway_and_invalid_inventory_fail_closed(self):
        self.assertEqual(review("10.250.30.0/26", inventory(), "10.250.30.63")["status"], "rejected")
        value = inventory(); value["docker_cidrs"] = ["malformed"]
        self.assertEqual(review("10.250.30.0/26", value)["status"], "rejected")
