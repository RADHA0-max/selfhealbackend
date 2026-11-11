"""Offline signal-to-diagnosis integration tests."""

import json
import unittest

from agent.diagnosis import DiagnosisError, diagnose
from agent.signal_adapter import (
    SignalValidationError,
    signal_to_evidence,
)
from experiments.offline_rpc import OfflineRPC


class TestSignalDiagnosisIntegration(unittest.TestCase):

    @staticmethod
    def response():
        return json.dumps({
            "category": "service_failure",
            "target": "api",
            "confidence": 0.9,
            "summary": "Synthetic API failure.",
            "recommended_action": "investigate_api",
        })

    def test_valid_signal_reaches_diagnosis(self):
        rpc = OfflineRPC(self.response())

        evidence = signal_to_evidence({
            "signal_id": "sig-api-001",
            "target": "api",
            "status": 503,
        })

        result = diagnose(rpc, evidence)

        self.assertEqual(result.category, "service_failure")
        self.assertEqual(result.target, "api")
        self.assertEqual(result.recommended_action, "investigate_api")
        self.assertEqual(len(rpc.calls), 1)

    def test_signal_identity_reaches_rpc_evidence(self):
        rpc = OfflineRPC(self.response())

        evidence = signal_to_evidence({
            "signal_id": "sig-api-002",
            "target": "api",
            "status": 503,
        })

        diagnose(rpc, evidence)

        messages = rpc.calls[0][1]
        user_message = messages[1]["content"]

        self.assertIn("sig-api-002", user_message)
        self.assertIn('"status":503', user_message)

    def test_invalid_signal_never_reaches_rpc(self):
        rpc = OfflineRPC(self.response())

        with self.assertRaises(SignalValidationError):
            evidence = signal_to_evidence({
                "signal_id": "../unsafe",
                "target": "api",
                "status": 503,
            })
            diagnose(rpc, evidence)

        self.assertEqual(rpc.calls, [])

    def test_invalid_model_response_is_rejected(self):
        rpc = OfflineRPC("invalid-json")

        evidence = signal_to_evidence({
            "signal_id": "sig-api-003",
            "target": "api",
            "status": 503,
        })

        with self.assertRaises(DiagnosisError):
            diagnose(rpc, evidence)

        self.assertEqual(len(rpc.calls), 1)


if __name__ == "__main__":
    unittest.main()
