"""Offline regression checks for Envoy access logging."""

from pathlib import Path
import unittest


CONFIG = (
    Path(__file__).resolve().parents[1]
    / "envoy"
    / "envoy.yaml"
)


class TestEnvoyLogging(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.config = CONFIG.read_text()

    def test_structured_stdout_logging(self):
        self.assertIn(
            "envoy.access_loggers.stdout",
            self.config,
        )
        self.assertIn("json_format:", self.config)

    def test_required_fields(self):
        fields = (
            "timestamp:",
            "client_ip:",
            "method:",
            "path:",
            "status:",
            "duration_ms:",
            "user_agent:",
            "request_id:",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertIn(field, self.config)

    def test_no_sensitive_header_logging(self):
        self.assertNotIn("%REQ(COOKIE)%", self.config)
        self.assertNotIn("%REQ(AUTHORIZATION)%", self.config)
        self.assertNotIn("cookie_present:", self.config)

    def test_existing_routing_preserved(self):
        self.assertIn("port_value: 10000", self.config)
        self.assertIn("address: testbed-app", self.config)
        self.assertIn("port_value: 18080", self.config)


if __name__ == "__main__":
    unittest.main()
