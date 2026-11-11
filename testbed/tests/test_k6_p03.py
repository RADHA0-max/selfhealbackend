"""Offline checks for P03 traffic scenario prototypes."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "k6"


class TestK6P03(unittest.TestCase):

    def test_new_scenarios_exist(self):
        for name in ("nat_control.js", "scraper.js"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())

    def test_scenarios_have_bounded_load(self):
        for name in ("nat_control.js", "scraper.js"):
            with self.subTest(name=name):
                content = (ROOT / name).read_text()
                self.assertIn("duration: '15s'", content)
                self.assertIn("timeout: '3s'", content)
                self.assertIn("TARGET_URL", content)
                self.assertIn("sleep(1)", content)

    def test_nat_has_distinct_logical_sessions(self):
        content = (ROOT / "nat_control.js").read_text()
        self.assertIn("nat-user-${__VU}", content)
        self.assertIn("X-Test-Session", content)
        self.assertIn("nat_negative_control", content)

    def test_scraper_has_identifiable_traffic(self):
        content = (ROOT / "scraper.js").read_text()
        self.assertIn("NanoClaw-Synthetic-Scraper", content)
        self.assertIn("synthetic_scraper", content)


    def test_organic_uses_batch_requests(self):
        content = (ROOT / "organic.js").read_text()
        self.assertIn("http.batch(", content)
        self.assertIn("/health", content)
        self.assertIn("/api/data", content)

    def test_organic_has_session_identity(self):
        content = (ROOT / "organic.js").read_text()
        self.assertIn("organic-user-${__VU}", content)
        self.assertIn("X-Test-Session", content)
        self.assertIn("vus: 1", content)
        self.assertIn("duration: '15s'", content)


if __name__ == "__main__":
    unittest.main()
