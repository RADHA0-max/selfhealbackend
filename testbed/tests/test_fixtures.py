"""Synthetic fixture integrity tests."""

import unittest

from testbed.fixtures import build_fixtures


class TestFixtures(unittest.TestCase):

    def test_unique_case_ids(self):
        cases = build_fixtures()
        self.assertEqual(len({c.case_id for c in cases}), len(cases))

    def test_expected_fixture_count(self):
        self.assertEqual(len(build_fixtures()), 6)

    def test_no_labels_inside_evidence(self):
        for case in build_fixtures():
            self.assertNotIn("expected_category", case.evidence)
            self.assertNotIn("expected_action", case.evidence)


if __name__ == "__main__":
    unittest.main()
