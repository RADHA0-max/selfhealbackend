"""Static safety checks for Person C's isolated infrastructure."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestInfrastructure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.compose = (ROOT / "compose.yaml").read_text()
        cls.envoy = (ROOT / "envoy" / "envoy.yaml").read_text()
        cls.k6 = (ROOT / "k6" / "baseline.js").read_text()

    def test_compose_project_isolated(self):
        self.assertIn(
            "name: nanoclaw-person-c-testbed",
            self.compose,
        )

    def test_compose_internal_network(self):
        self.assertIn("internal: true", self.compose)

    def test_no_host_ports(self):
        self.assertNotIn("\n    ports:", self.compose)

    def test_read_only_containers(self):
        self.assertEqual(
            self.compose.count("read_only: true"),
            2,
        )

    def test_envoy_upstream(self):
        self.assertIn("address: testbed-app", self.envoy)
        self.assertIn("port_value: 18080", self.envoy)

    def test_envoy_listener(self):
        self.assertIn("port_value: 10000", self.envoy)

    def test_k6_bounded_load(self):
        self.assertIn("vus: 1", self.k6)
        self.assertIn("duration: '10s'", self.k6)

    def test_k6_targets_api(self):
        self.assertIn("/api/data", self.k6)


if __name__ == "__main__":
    unittest.main()
