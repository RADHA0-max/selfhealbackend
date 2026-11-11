"""Offline Ollama response envelope validation tests."""

import unittest

from ollama.adapter import OllamaResponseError, extract_response


class TestOllamaEnvelope(unittest.TestCase):

    def test_accept_complete_response(self):
        payload = {
            "done": True,
            "message": {"content": "{}"},
        }
        self.assertEqual(extract_response(payload), "{}")

    def test_reject_incomplete_response(self):
        payload = {
            "done": False,
            "message": {"content": "{}"},
        }
        with self.assertRaises(OllamaResponseError):
            extract_response(payload)

    def test_reject_explicit_error(self):
        payload = {
            "error": "model unavailable",
            "message": {"content": "{}"},
        }
        with self.assertRaises(OllamaResponseError):
            extract_response(payload)

    def test_reject_invalid_done(self):
        payload = {
            "done": "true",
            "message": {"content": "{}"},
        }
        with self.assertRaises(OllamaResponseError):
            extract_response(payload)


if __name__ == "__main__":
    unittest.main()
