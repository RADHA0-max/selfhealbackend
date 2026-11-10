"""Offline experiment runner tests."""

import json
import unittest

from experiments.runner import run_experiment
from testbed.fixtures import build_fixtures


class FakeRPC:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def call(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        return {"ok": True, "content": self.response}


class TestRunner(unittest.TestCase):

    def test_valid_diagnosis(self):
        case = build_fixtures()[0]
        response = json.dumps({
            "category": case.expected_category,
            "target": case.expected_target,
            "confidence": 0.9,
            "summary": "Synthetic incident.",
            "recommended_action": case.expected_action,
        })
        rpc = FakeRPC(response)

        report = run_experiment((case,), rpc)

        self.assertEqual(report["completed"], 1)
        self.assertEqual(report["scores"]["category_correct"], 1.0)
        self.assertIsNone(report["recovery_success"])
        self.assertEqual(len(rpc.calls), 1)

    def test_invalid_response(self):
        rpc = FakeRPC("not JSON")
        report = run_experiment(build_fixtures(), rpc)

        self.assertEqual(report["completed"], 0)
        self.assertEqual(report["scores"]["category_correct"], 0.0)

    def test_no_ground_truth_in_evidence(self):
        case = build_fixtures()[0]
        rpc = FakeRPC("{}")

        run_experiment((case,), rpc)

        prompt = rpc.calls[0][1][1]["content"]
        self.assertNotIn("expected_category", prompt)
        self.assertNotIn("expected_action", prompt)
        self.assertNotIn("DB-503", prompt)


if __name__ == "__main__":
    unittest.main()
