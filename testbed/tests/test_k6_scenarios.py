"""Offline checks for bounded Person C k6 scenarios."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "k6"


class TestK6Scenarios(unittest.TestCase):

    def test_expected_scenarios_exist(self):
        expected = {
            "baseline.js",
            "organic.js",
            "burst.js",
            "cache.js",
            "parallel.js",
        }
        actual = {path.name for path in ROOT.glob("*.js")}
        self.assertTrue(expected.issubset(actual))

    def test_scripts_use_explicit_target(self):
        for path in ROOT.glob("*.js"):
            with self.subTest(script=path.name):
                content = path.read_text()
                self.assertIn("TARGET_URL", content)

    def test_scripts_have_bounded_duration(self):
        for path in ROOT.glob("*.js"):
            with self.subTest(script=path.name):
                content = path.read_text()
                self.assertIn("duration:", content)

    def test_scripts_have_request_timeout(self):
        for path in ROOT.glob("*.js"):
            with self.subTest(script=path.name):
                content = path.read_text()
                self.assertIn("timeout: '3s'", content)

    def test_parallel_uses_batch(self):
        content = (ROOT / "parallel.js").read_text()
        self.assertIn("http.batch(", content)

    def test_burst_is_bounded(self):
        content = (ROOT / "burst.js").read_text()
        self.assertIn("target: 3", content)
        self.assertNotIn("target: 100", content)


if __name__ == "__main__":
    unittest.main()
