"""Tests for bounded offline diagnosis failure classification."""

import unittest

from agent.diagnosis import DiagnosisError
from agent.rpc_client import RPCError, RPCTimeout
from experiments.failure_classification import classify_failure


class TestFailureClassification(unittest.TestCase):

    def test_invalid_json(self):
        self.assertEqual(
            classify_failure(DiagnosisError("invalid diagnosis JSON")),
            "invalid_json",
        )

    def test_invalid_schema(self):
        self.assertEqual(
            classify_failure(DiagnosisError("unexpected diagnosis fields")),
            "invalid_schema",
        )

    def test_duplicate_field(self):
        self.assertEqual(
            classify_failure(DiagnosisError("duplicate diagnosis field")),
            "invalid_schema",
        )

    def test_rpc_error(self):
        self.assertEqual(
            classify_failure(RPCError("request failed")),
            "transport_error",
        )

    def test_rpc_timeout(self):
        self.assertEqual(
            classify_failure(RPCTimeout("request timed out")),
            "transport_error",
        )

    def test_builtin_timeout(self):
        self.assertEqual(
            classify_failure(TimeoutError()),
            "transport_error",
        )

    def test_unexpected_error(self):
        self.assertEqual(
            classify_failure(RuntimeError("unexpected")),
            "agent_error",
        )


if __name__ == "__main__":
    unittest.main()
