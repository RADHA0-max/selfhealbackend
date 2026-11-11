"""Offline tests for the isolated target application."""

import io
import json
import unittest
from unittest.mock import Mock

from testbed.app.server import TargetHandler


def request(path):
    """Exercise the HTTP handler without opening a socket."""
    handler = TargetHandler.__new__(TargetHandler)
    handler.path = path
    handler.wfile = io.BytesIO()

    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()

    handler.do_GET()

    status = handler.send_response.call_args[0][0]
    payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

    return status, payload


class TestTargetApplication(unittest.TestCase):

    def test_health(self):
        status, payload = request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "healthy"})

    def test_readiness(self):
        status, payload = request("/ready")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ready": True})

    def test_api_data(self):
        status, payload = request("/api/data")
        self.assertEqual(status, 200)
        self.assertEqual(payload["service"], "nanoclaw-testbed")
        self.assertEqual(payload["items"], [])

    def test_unknown_endpoint(self):
        status, payload = request("/missing")
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "not_found"})


if __name__ == "__main__":
    unittest.main()
