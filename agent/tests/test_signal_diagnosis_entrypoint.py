"""P03.4 offline tests for the validated diagnosis entry point."""

import json
import unittest

from agent.diagnosis import DiagnosisError
from agent.signal_adapter import SignalValidationError
from agent.signal_diagnosis import diagnose_signal
from experiments.offline_rpc import OfflineRPC


class TestSignalDiagnosisEntrypoint(unittest.TestCase):

    @staticmethod
    def response():
        return json.dumps({
            "category": "service_failure",
            "target": "api",
            "confidence": 0.9,
            "summary": "Synthetic API failure.",
            "recommended_action": "investigate_api",
        })

    @staticmethod
    def signal():
        return {
            "signal_id": "sig-api-001",
            "target": "api",
            "status": 503,
        }

    def test_valid_signal(self):
        rpc = OfflineRPC(self.response())
        result = diagnose_signal(rpc, self.signal())

        self.assertEqual(result.target, "api")
        self.assertEqual(result.category, "service_failure")
        self.assertEqual(len(rpc.calls), 1)

    def test_invalid_signal_blocks_rpc(self):
        rpc = OfflineRPC(self.response())
        signal = self.signal()
        signal["status"] = "503"

        with self.assertRaises(SignalValidationError):
            diagnose_signal(rpc, signal)

        self.assertEqual(rpc.calls, [])

    def test_unknown_field_blocks_rpc(self):
        rpc = OfflineRPC(self.response())
        signal = self.signal()
        signal["command"] = "execute"

        with self.assertRaises(SignalValidationError):
            diagnose_signal(rpc, signal)

        self.assertEqual(rpc.calls, [])

    def test_invalid_model_response(self):
        rpc = OfflineRPC("invalid-json")

        with self.assertRaises(DiagnosisError):
            diagnose_signal(rpc, self.signal())

        self.assertEqual(len(rpc.calls), 1)

    def test_signal_id_preserved(self):
        rpc = OfflineRPC(self.response())
        diagnose_signal(rpc, self.signal())

        messages = rpc.calls[0][1]
        self.assertIn(
            "sig-api-001",
            messages[1]["content"],
        )


if __name__ == "__main__":
    unittest.main()
