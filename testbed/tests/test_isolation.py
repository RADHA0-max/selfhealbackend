"""Offline isolation checks for Person C infrastructure."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestIsolation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.compose = (ROOT / "compose.yaml").read_text()
        cls.envoy = (ROOT / "envoy" / "envoy.yaml").read_text()

    def test_application_mount_is_scoped(self):
        self.assertIn(
            "./:/workspace/testbed:ro",
            self.compose,
        )

    def test_repository_root_not_mounted(self):
        self.assertNotIn(
            "../:/workspace:ro",
            self.compose,
        )

    def test_envoy_admin_disabled(self):
        self.assertNotIn("\nadmin:", self.envoy)

    def test_no_host_ports(self):
        self.assertNotIn("\n    ports:", self.compose)

    def test_network_is_internal(self):
        self.assertIn("internal: true", self.compose)

    def test_no_privileged_containers(self):
        self.assertNotIn("privileged: true", self.compose)


if __name__ == "__main__":
    unittest.main()
