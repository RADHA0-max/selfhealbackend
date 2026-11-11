"""Offline checks for testbed container runtime settings."""

from pathlib import Path
import unittest


COMPOSE = Path(__file__).resolve().parents[1] / "compose.yaml"


class TestComposeRuntime(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.config = COMPOSE.read_text()

    def test_python_bytecode_disabled(self):
        self.assertIn(
            'PYTHONDONTWRITEBYTECODE: "1"',
            self.config,
        )

    def test_envoy_config_path(self):
        self.assertIn(
            "- /etc/envoy/envoy.yaml",
            self.config,
        )

    def test_no_duplicate_envoy_executable(self):
        self.assertNotIn(
            "      - envoy\n      - -c",
            self.config,
        )

    def test_no_host_port_publication(self):
        self.assertNotIn(
            "\n    ports:",
            self.config,
        )

    def test_internal_network(self):
        self.assertIn(
            "internal: true",
            self.config,
        )


if __name__ == "__main__":
    unittest.main()
