"""Bounded loopback HTTP integration tests; no Docker or shared services."""

from __future__ import annotations

import json
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from testbed.app.faults import FaultController
from testbed.app.server import TargetHandler


@contextmanager
def local_testbed(mode):
    """Start a loopback-only ephemeral test server."""
    class IsolatedHandler(TargetHandler):
        fault_controller = FaultController(mode)

    server = ThreadingHTTPServer(("127.0.0.1", 0), IsolatedHandler)
    server.daemon_threads = True

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def get(port, path):
    opener = build_opener(ProxyHandler({}))
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        method="GET",
    )

    started = time.monotonic()

    try:
        response = opener.open(request, timeout=2)
    except HTTPError as error:
        response = error

    with response:
        body = response.read(4096)
        status = response.status

    elapsed_ms = (time.monotonic() - started) * 1000
    return status, json.loads(body), elapsed_ms


class RealHTTPTests(unittest.TestCase):

    def test_health_is_healthy_during_outage(self):
        with local_testbed("outage") as port:
            status, body, _ = get(port, "/health")
            self.assertEqual(status, 200)
            self.assertEqual(body, {"status": "healthy"})

    def test_ready_outage(self):
        with local_testbed("outage") as port:
            status, body, _ = get(port, "/ready")
            self.assertEqual(status, 503)
            self.assertEqual(body, {"ready": False})

    def test_timeout_response(self):
        with local_testbed("timeout_response") as port:
            status, body, _ = get(port, "/ready")
            self.assertEqual(status, 504)
            self.assertEqual(body, {"ready": False})

    def test_real_latency(self):
        with local_testbed("latency") as port:
            status, _, elapsed_ms = get(port, "/ready")
            self.assertEqual(status, 200)
            self.assertGreaterEqual(elapsed_ms, 200)
            self.assertLess(elapsed_ms, 2000)

    def test_recovery_sequence(self):
        with local_testbed("recovering") as port:
            statuses = [get(port, "/ready")[0] for _ in range(7)]
            self.assertEqual(statuses, [503, 503, 503, 200, 200, 200, 200])

    def test_regression_sequence(self):
        with local_testbed("regression") as port:
            statuses = [get(port, "/ready")[0] for _ in range(9)]
            self.assertEqual(
                statuses,
                [503, 503, 503, 200, 200, 200, 503, 503, 503],
            )

    def test_unknown_path(self):
        with local_testbed("healthy") as port:
            status, body, _ = get(port, "/does-not-exist")
            self.assertEqual(status, 404)
            self.assertEqual(body, {"error": "not_found"})

    def test_api_data(self):
        with local_testbed("healthy") as port:
            status, body, _ = get(port, "/api/data")
            self.assertEqual(status, 200)
            self.assertEqual(body["service"], "nanoclaw-testbed")


if __name__ == "__main__":
    unittest.main()
