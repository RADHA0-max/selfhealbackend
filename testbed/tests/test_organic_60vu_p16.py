"""Static safety checks for the opt-in 60-VU organic workload."""

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "k6" / "organic_60vu_p16.js"


class TestOrganic60VUP16(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text()

    def test_explicit_60_vus(self):
        self.assertRegex(self.source, r"\bvus:\s*60\b")

    def test_bounded_duration(self):
        self.assertRegex(self.source, r"duration:\s*'30s'")

    def test_target_allowlist(self):
        self.assertIn("safeTarget(", self.source)

    def test_no_external_urls(self):
        self.assertNotIn("https://", self.source)

    def test_no_unbounded_loop(self):
        self.assertNotRegex(
            self.source,
            r"\bwhile\s*\(|\bfor\s*\(\s*;\s*;",
        )

    def test_explicit_timeout(self):
        self.assertIn("timeout: '3s'", self.source)

    def test_session_per_vu(self):
        self.assertIn("organic-vu-${vu}", self.source)

    def test_no_host_port_publication(self):
        self.assertNotIn("0.0.0.0", self.source)

    def test_bounded_paths(self):
        for path in ("/health", "/ready", "/api/data"):
            self.assertIn(path, self.source)

    def test_no_automatic_execution(self):
        self.assertNotIn("exec(", self.source)


if __name__ == "__main__":
    unittest.main()
