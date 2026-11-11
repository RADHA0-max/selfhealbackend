"""Security regression tests for offline Ollama diagnosis validation."""

import json
import unittest

from agent.diagnosis import Diagnosis
from ollama.adapter import OllamaResponseError, parse_diagnosis


VALID = {
    "category": "dependency_failure",
    "target": "database",
    "confidence": 0.9,
    "summary": "Database dependency unavailable.",
    "recommended_action": "investigate_database",
}


def wrap(content):
    return {"message": {"content": content}}


class TestAdapterSecurity(unittest.TestCase):

    def test_returns_validated_diagnosis(self):
        result = parse_diagnosis(wrap(json.dumps(VALID)))
        self.assertIsInstance(result, Diagnosis)
        self.assertEqual(result.target, "database")

    def test_reject_unknown_category(self):
        data = dict(VALID, category="execute_shell")

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(json.dumps(data)))

    def test_reject_unknown_action(self):
        data = dict(VALID, recommended_action="docker_restart")

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(json.dumps(data)))

    def test_reject_confidence_out_of_range(self):
        data = dict(VALID, confidence=500)

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(json.dumps(data)))

    def test_reject_boolean_confidence(self):
        data = dict(VALID, confidence=True)

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(json.dumps(data)))

    def test_reject_empty_summary(self):
        data = dict(VALID, summary="   ")

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(json.dumps(data)))

    def test_reject_duplicate_json_fields(self):
        raw = json.dumps(VALID).replace(
            '"confidence": 0.9',
            '"confidence": 0.9, "confidence": 0.1',
        )

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(raw))

    def test_reject_nonfinite_confidence(self):
        data = dict(VALID, confidence=float("nan"))

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(json.dumps(data)))

    def test_reject_markdown_response(self):
        raw = "```json\n" + json.dumps(VALID) + "\n```"

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(wrap(raw))


if __name__ == "__main__":
    unittest.main()
