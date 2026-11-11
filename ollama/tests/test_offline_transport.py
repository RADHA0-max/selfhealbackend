"""Offline end-to-end tests for the Ollama diagnosis transport."""

import json
import unittest

from agent.diagnosis import DiagnosisError, diagnose
from ollama.offline_transport import OfflineOllamaTransport


VALID_DIAGNOSIS = {
    "category": "dependency_failure",
    "target": "database",
    "confidence": 0.92,
    "summary": "Database dependency unavailable.",
    "recommended_action": "investigate_database",
}


def response(content, done=True):
    return {
        "done": done,
        "message": {"content": content},
    }


class TestOfflineTransport(unittest.TestCase):

    def test_end_to_end_diagnosis(self):
        transport = OfflineOllamaTransport(
            response(json.dumps(VALID_DIAGNOSIS))
        )

        result = diagnose(
            transport,
            {
                "api_status": 503,
                "database_status": 503,
            },
        )

        self.assertEqual(result.category, "dependency_failure")
        self.assertEqual(result.target, "database")
        self.assertEqual(result.recommended_action, "investigate_database")

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["model"], "fast")

    def test_reject_invalid_model_output(self):
        invalid = dict(
            VALID_DIAGNOSIS,
            recommended_action="execute_shell",
        )

        transport = OfflineOllamaTransport(
            response(json.dumps(invalid))
        )

        with self.assertRaises(DiagnosisError):
            diagnose(transport, {"api_status": 503})

    def test_reject_incomplete_response(self):
        transport = OfflineOllamaTransport(
            response(json.dumps(VALID_DIAGNOSIS), done=False)
        )

        with self.assertRaises(DiagnosisError):
            diagnose(transport, {"api_status": 503})

    def test_reject_unsupported_model(self):
        transport = OfflineOllamaTransport(
            response(json.dumps(VALID_DIAGNOSIS))
        )

        with self.assertRaises(ValueError):
            transport.call("unknown", [])


if __name__ == "__main__":
    unittest.main()
