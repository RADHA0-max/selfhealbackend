"""Regression tests for reconstructed P05.13 pilot comparison."""

import unittest

from experiments.p05_pilot_gate_comparison import compare


class PilotGateComparisonTests(unittest.TestCase):

    def test_reconstructed_pilot_results(self):
        report = compare()

        self.assertEqual(
            report["evaluation_mode"],
            "reconstructed_pilot_offline",
        )
        self.assertFalse(report["inference_verified"])
        self.assertIsNone(report["recovery_success"])

        self.assertEqual(report["requested"], 5)
        self.assertEqual(report["raw_exact_matches"], 2)
        self.assertEqual(report["gated_exact_matches"], 2)
        self.assertEqual(report["downgraded"], 3)

        rows = report["rows"]

        self.assertEqual(len(rows), 5)
        self.assertEqual(
            [row["case_id"] for row in rows],
            [
                "p05-synthetic-001",
                "p05-synthetic-002",
                "p05-synthetic-003",
                "p05-synthetic-004",
                "p05-synthetic-005",
            ],
        )

        self.assertEqual(
            [
                row["case_id"]
                for row in rows
                if row["downgraded"]
            ],
            [
                "p05-synthetic-001",
                "p05-synthetic-002",
                "p05-synthetic-004",
            ],
        )

        for row in rows:
            if row["downgraded"]:
                self.assertEqual(row["gated_category"], "unknown")


if __name__ == "__main__":
    unittest.main()
