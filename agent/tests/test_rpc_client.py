import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.rpc_client import RPCClient, RPCError, RPCTimeout
from broker.protocol import make_response


class TestRPCClient(unittest.TestCase):

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
            timeout=0.5,
            poll_interval=0.01,
        )

    def test_successful_request(self):
        def fake_broker():
            deadline = time.monotonic() + 2

            while time.monotonic() < deadline:
                requests = list(self.in_dir.glob("req-*.json"))

                if requests:
                    request = json.loads(requests[0].read_text())
                    response = make_response(
                        request["request_id"],
                        content='{"diagnosis":"synthetic"}',
                    )

                    destination = (
                        self.out_dir
                        / f'resp-{request["request_id"]}.json'
                    )
                    destination.write_bytes(response)
                    return

                time.sleep(0.01)

        worker = threading.Thread(target=fake_broker)
        worker.start()

        try:
            response = self.client.call(
                "fast",
                [{"role": "user", "content": "Synthetic incident"}],
            )
        finally:
            worker.join(timeout=2)

        self.assertTrue(response["ok"])
        self.assertIn("synthetic", response["content"])

    def test_timeout_does_not_retry(self):
        with self.assertRaises(RPCTimeout):
            self.client.call(
                "fast",
                [{"role": "user", "content": "No broker running"}],
            )

        self.assertEqual(
            len(list(self.in_dir.glob("req-*.json"))),
            1,
        )

    def test_reject_invalid_model(self):
        with self.assertRaises(ValueError):
            self.client.call(
                "unapproved-model",
                [{"role": "user", "content": "Test"}],
            )

        self.assertEqual(
            len(list(self.in_dir.glob("req-*.json"))),
            0,
        )

    def test_reject_oversized_request(self):
        with self.assertRaises(ValueError):
            self.client.call(
                "fast",
                [{"role": "user", "content": "X" * 70000}],
            )

        self.assertEqual(
            len(list(self.in_dir.glob("req-*.json"))),
            0,
        )


if __name__ == "__main__":
    unittest.main()
