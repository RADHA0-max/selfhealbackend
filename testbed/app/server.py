"""Minimal HTTP target for the isolated NanoClaw testbed."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class TargetHandler(BaseHTTPRequestHandler):
    """Deterministic HTTP endpoints for controlled experiments."""

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "healthy"})
        elif self.path == "/ready":
            self._send_json(200, {"ready": True})
        elif self.path == "/api/data":
            self._send_json(200, {
                "service": "nanoclaw-testbed",
                "items": [],
            })
        else:
            self._send_json(404, {"error": "not_found"})

    def _send_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Disable request logging to avoid unnecessary shared-server noise."""
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    server = ThreadingHTTPServer((args.host, args.port), TargetHandler)

    try:
        print(
            "Person C testbed listening on {}:{}".format(
                args.host, args.port
            ),
            flush=True,
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
