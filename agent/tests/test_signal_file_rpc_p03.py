"""Offline signal-to-file-RPC integration tests."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.diagnosis import DiagnosisError
from agent.rpc_client import RPCClient, RPCError
from agent.signal_adapter import SignalValidationError
from agent.signal_diagnosis import diagnose_signal
from broker.protocol import make_response


class TestSignalFileRPC(unittest.TestCase):

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
            timeout=1.0,
            poll_interval=0.01,
        )

    @staticmethod
    def signal():
        return {
            "signal_id": "sig-api-001",
            "target": "api",
            "status": 503,
        }

    @staticmethod
    def diagnosis():
        return json.dumps({
            "category": "service_failure",
            "target": "api",
            "confidence": 0.9,
            "summary": "Synthetic API failure.",
            "recommended_action": "investigate_api",
        })

    def run_with_broker(self, response_factory):
        errors = []

        def fake_broker():
            try:
                deadline = time.monotonic() + 2.0

                while time.monotonic() < deadline:
                    requests = list(self.in_dir.glob("req-*.json"))

                    if requests:
                        request = json.loads(
                            requests[0].read_text()
                        )

                        request_id = request["request_id"]
                        response = response_factory(request_id)

                        destination = (
                            self.out_dir
                            / f"resp-{request_id}.json"
                        )

                        temporary = self.out_dir / (
                            f".tmp-{request_id}"
                        )
                        temporary.write_bytes(response)
                        temporary.replace(destination)
                        return

                    time.sleep(0.01)

                errors.append("mock broker did not receive request")
            except Exception as exc:
                errors.append(str(exc))

        worker = threading.Thread(target=fake_broker)
        worker.start()

        try:
            return diagnose_signal(
                self.client,
                self.signal(),
            )
        finally:
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])

    def test_successful_diagnosis(self):
        result = self.run_with_broker(
            lambda request_id: make_response(
                request_id,
                content=self.diagnosis(),
            )
        )

        self.assertEqual(result.category, "service_failure")
        self.assertEqual(result.target, "api")

    def test_invalid_signal_does_not_publish_request(self):
        signal = self.signal()
        signal["status"] = "503"

        with self.assertRaises(SignalValidationError):
            diagnose_signal(self.client, signal)

        self.assertEqual(
            list(self.in_dir.glob("req-*.json")),
            [],
        )

    def test_malformed_model_output_rejected(self):
        with self.assertRaises(DiagnosisError):
            self.run_with_broker(
                lambda request_id: make_response(
                    request_id,
                    content="invalid-json",
                )
            )

    def test_mismatched_request_id_rejected(self):
        with self.assertRaises(RPCError):
            self.run_with_broker(
                lambda request_id: make_response(
                    "wrong-id",
                    content=self.diagnosis(),
                )
            )


if __name__ == "__main__":
    unittest.main()
