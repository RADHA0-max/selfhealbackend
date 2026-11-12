"""Offline end-to-end test of the file-RPC diagnosis runner."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.file_rpc_diagnosis import diagnose_file_rpc
from broker.protocol import make_response


class TestFileRPCRunnerIntegration(unittest.TestCase):

    def test_valid_signal_through_file_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "in"
            outgoing = root / "out"
            incoming.mkdir()
            outgoing.mkdir()

            errors = []
            observed = []

            def fake_broker():
                try:
                    deadline = time.monotonic() + 3

                    while time.monotonic() < deadline:
                        requests = list(incoming.glob("req-*.json"))

                        if requests:
                            request = json.loads(
                                requests[0].read_text()
                            )
                            observed.append(request)

                            diagnosis = json.dumps({
                                "category": "service_failure",
                                "target": "api",
                                "confidence": 0.95,
                                "summary": "Synthetic API failure",
                                "recommended_action": "investigate_api",
                            })

                            response = make_response(
                                request["request_id"],
                                content=diagnosis,
                            )

                            destination = outgoing / (
                                f'resp-{request["request_id"]}.json'
                            )
                            temporary = outgoing / (
                                f'.tmp-{request["request_id"]}'
                            )

                            temporary.write_bytes(response)
                            temporary.replace(destination)
                            return

                        time.sleep(0.01)

                    errors.append("Broker did not receive request")
                except Exception as exc:
                    errors.append(str(exc))

            worker = threading.Thread(target=fake_broker)
            worker.start()

            try:
                result = diagnose_file_rpc(
                    {
                        "signal_id": "p04-api-001",
                        "target": "api",
                        "status": 503,
                    },
                    incoming,
                    outgoing,
                    timeout=2.0,
                )
            finally:
                worker.join(timeout=4)

            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(observed), 1)
            self.assertEqual(result.category, "service_failure")
            self.assertEqual(result.target, "api")
            self.assertEqual(
                result.recommended_action,
                "investigate_api",
            )

            request_text = json.dumps(observed[0])
            self.assertIn("p04-api-001", request_text)
            self.assertIn("503", request_text)


if __name__ == "__main__":
    unittest.main()
