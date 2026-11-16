"""Offline tests for P06 reliability reporting."""

import unittest

from experiments.reliability_report_p06 import summarize_reliability


def make_record():
    rows = []

    for index in range(100):
        case_id = "case-{:03d}".format(index)
        status = "ok" if index < 90 else "invalid_decision"

        rows.append({
            "case_id": case_id,
            "status": status,
            "category_correct": index < 80,
            "target_correct": index < 80,
            "action_correct": index < 80,
        })

    return {
        "evaluation_mode": "recorded_capture_offline",
        "dataset_type": "synthetic",
        "inference_verified": False,
        "recovery_success": None,
        "requested": 100,
        "completed": 95,
        "partial_responses": {
            "case-{:03d}".format(i): "{}"
            for i in range(95)
        },
        "failures": {
            "case-{:03d}".format(i): "TimeoutError"
            for i in range(95, 100)
        },
        "evaluation": {
            "requested": 100,
            "completed": 90,
            "results": rows,
        },
    }


class ReliabilityReportTests(unittest.TestCase):

    def test_reports_distinct_reliability_metrics(self):
        report = summarize_reliability(make_record())

        self.assertEqual(report["captured_responses"], 95)
        self.assertEqual(report["missing_responses"], 5)
        self.assertEqual(report["schema_valid_diagnoses"], 90)
        self.assertEqual(report["schema_invalid_captured_responses"], 5)
        self.assertEqual(report["exact_matches"], 80)
        self.assertEqual(report["schema_validity_rate_all_requests"], 0.9)

    def test_rejects_inconsistent_accounting(self):
        record = make_record()
        record["completed"] = 99

        with self.assertRaises(ValueError):
            summarize_reliability(record)

    def test_rejects_unverified_recovery_claim(self):
        record = make_record()
        record["recovery_success"] = True

        with self.assertRaises(ValueError):
            summarize_reliability(record)


if __name__ == "__main__":
    unittest.main()
