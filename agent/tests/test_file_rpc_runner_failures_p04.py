"""Offline failure-path tests for the file-RPC diagnosis runner."""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.diagnosis import DiagnosisError
from agent.file_rpc_diagnosis import diagnose_file_rpc
from agent.rpc_client import RPCError, RPCTimeout
from agent.signal_adapter import SignalValidationError
from broker.protocol import make_response


SIGNAL = {
    "signal_id": "p04-failure-001",
    "target": "api",
    "status": 503,
}


class TestFileRPCRunnerFailures(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        root = Path(self.temp.name)
        self.incoming = root / "in"
        self.outgoing = root / "out"
        self.incoming.mkdir()
        self.outgoing.mkdir()

    def run_with_broker(self, response_factory):
        errors = []

        def fake_broker():
            try:
                deadline = time.monotonic() + 2.0

                while time.monotonic() < deadline:
                    requests = list(
                        self.incoming.glob("req-*.json")
                    )

                    if requests:
                        request_id = requests[0].stem[4:]

                        response = response_factory(request_id)

                        destination = self.outgoing / (
                            f"resp-{request_id}.json"
                        )
                        temporary = self.outgoing / (
                            f".tmp-{request_id}"
                        )

                        temporary.write_bytes(response)
                        temporary.replace(destination)
                        return

                    time.sleep(0.01)

                errors.append("broker did not receive request")

            except Exception as exc:
                errors.append(str(exc))

        worker = threading.Thread(target=fake_broker)
        worker.start()

        try:
            return diagnose_file_rpc(
                SIGNAL,
                self.incoming,
                self.outgoing,
                timeout=1.0,
            )
        finally:
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])

    def test_invalid_diagnosis_json_rejected(self):
        with self.assertRaises(DiagnosisError):
            self.run_with_broker(
                lambda request_id: make_response(
                    request_id,
                    content="not-json",
                )
            )

        self.assertEqual(
            len(list(self.incoming.glob("req-*.json"))),
            1,
        )

    def test_broker_error_rejected(self):
        with self.assertRaises(RPCError):
            self.run_with_broker(
                lambda request_id: make_response(
                    request_id,
                    error="synthetic broker failure",
                )
            )

        self.assertEqual(
            len(list(self.incoming.glob("req-*.json"))),
            1,
        )

    def test_malformed_broker_response_rejected(self):
        with self.assertRaises(RPCError):
            self.run_with_broker(
                lambda request_id: b"{invalid-json",
            )

        self.assertEqual(
            len(list(self.incoming.glob("req-*.json"))),
            1,
        )

    def test_timeout_does_not_retry(self):
        with self.assertRaises(RPCTimeout):
            diagnose_file_rpc(
                SIGNAL,
                self.incoming,
                self.outgoing,
                timeout=0.1,
            )

        self.assertEqual(
            len(list(self.incoming.glob("req-*.json"))),
            1,
        )

    def test_invalid_signal_does_not_publish(self):
        invalid = dict(SIGNAL)
        invalid["status"] = "503"

        with self.assertRaises(SignalValidationError):
            diagnose_file_rpc(
                invalid,
                self.incoming,
                self.outgoing,
                timeout=0.1,
            )

        self.assertEqual(
            list(self.incoming.glob("req-*.json")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
