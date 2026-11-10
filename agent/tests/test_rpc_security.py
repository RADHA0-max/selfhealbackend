"""Adversarial tests for NanoClaw file-RPC responses."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.rpc_client import RPCClient, RPCError


class TestRPCSecurity(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.in_dir = root / "in"
        self.out_dir = root / "out"

        self.in_dir.mkdir()
        self.out_dir.mkdir()

        self.client = RPCClient(
            self.in_dir,
            self.out_dir,
            timeout=1,
            poll_interval=0.01,
        )

    def simulate_response(self, response_factory):
        """Run one synthetic response against a temporary RPC queue."""

        def fake_broker():
            deadline = time.monotonic() + 2

            while time.monotonic() < deadline:
                requests = list(self.in_dir.glob("req-*.json"))

                if requests:
                    request = json.loads(requests[0].read_text())
                    request_id = request["request_id"]

                    response = response_factory(request_id)

                    response_path = (
                        self.out_dir / f"resp-{request_id}.json"
                    )

                    response_path.write_bytes(response)
                    return

                time.sleep(0.01)

        worker = threading.Thread(target=fake_broker)
        worker.start()

        try:
            return self.client.call(
                "fast",
                [{"role": "user", "content": "Synthetic incident"}],
            )
        finally:
            worker.join(timeout=2)

    @staticmethod
    def valid_response(request_id):
        return {
            "request_id": request_id,
            "ok": True,
            "content": "Synthetic diagnosis",
            "embedding": None,
            "error": None,
        }

    def test_reject_mismatched_request_id(self):
        def response_factory(request_id):
            response = self.valid_response(request_id)
            response["request_id"] = "wrong-id"
            return json.dumps(response).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(response_factory)

    def test_reject_duplicate_response_fields(self):
        def response_factory(request_id):
            return (
                '{"request_id":"%s","ok":true,"ok":false,'
                '"content":"test","embedding":null,"error":null}'
                % request_id
            ).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(response_factory)

    def test_reject_oversized_response(self):
        def response_factory(request_id):
            response = self.valid_response(request_id)
            response["content"] = "X" * 70000
            return json.dumps(response).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(response_factory)

    def test_reject_nan_embedding(self):
        def response_factory(request_id):
            response = self.valid_response(request_id)
            response["embedding"] = [float("nan")]
            return json.dumps(response).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(response_factory)

    def test_reject_success_with_error(self):
        def response_factory(request_id):
            response = self.valid_response(request_id)
            response["error"] = "Unexpected error"
            return json.dumps(response).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(response_factory)


if __name__ == "__main__":
    unittest.main()
