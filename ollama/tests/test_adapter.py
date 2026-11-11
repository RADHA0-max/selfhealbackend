"""Offline tests for the Ollama response adapter."""

import json
import unittest

from ollama.adapter import (
    MAX_RESPONSE_BYTES,
    OllamaResponseError,
    extract_response,
    parse_diagnosis,
)


VALID_DIAGNOSIS = {
    "category": "dependency_failure",
    "target": "database",
    "confidence": 0.9,
    "summary": "Database availability degraded",
    "recommended_action": "investigate_database",
}


def payload(content):
    return {"message": {"content": content}}


class TestOllamaAdapter(unittest.TestCase):

    def test_extract_valid_response(self):
        result = extract_response(payload("{}"))
        self.assertEqual(result, "{}")

    def test_reject_missing_message(self):
        with self.assertRaises(OllamaResponseError):
            extract_response({})

    def test_reject_non_text_content(self):
        with self.assertRaises(OllamaResponseError):
            extract_response(payload(123))

    def test_reject_oversized_response(self):
        with self.assertRaises(OllamaResponseError):
            extract_response(payload("x" * (MAX_RESPONSE_BYTES + 1)))

    def test_parse_valid_diagnosis(self):
        result = parse_diagnosis(
            payload(json.dumps(VALID_DIAGNOSIS))
        )
        self.assertEqual(result.target, 'database')
        self.assertEqual(result.confidence, 0.9)

    def test_reject_invalid_json(self):
        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(payload("not json"))

    def test_reject_extra_fields(self):
        diagnosis = dict(VALID_DIAGNOSIS)
        diagnosis["execute"] = True

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(payload(json.dumps(diagnosis)))

    def test_reject_missing_fields(self):
        diagnosis = dict(VALID_DIAGNOSIS)
        del diagnosis["confidence"]

        with self.assertRaises(OllamaResponseError):
            parse_diagnosis(payload(json.dumps(diagnosis)))


if __name__ == "__main__":
    unittest.main()
