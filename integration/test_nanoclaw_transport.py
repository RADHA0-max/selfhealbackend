import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from integration.nanoclaw_transport import NanoClawTransport, NanoClawTransportError


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "data").mkdir()
        mailbox = root / "data/v2-sessions/group/session"
        mailbox.mkdir(parents=True)
        self.inbound = mailbox / "inbound.db"
        self.outbound = mailbox / "outbound.db"

        with sqlite3.connect(self.inbound) as db:
            db.execute("""
                CREATE TABLE messages_in (
                    id TEXT, channel_type TEXT,
                    platform_id TEXT, content TEXT
                )
            """)

        with sqlite3.connect(self.outbound) as db:
            db.execute("""
                CREATE TABLE messages_out (
                    seq INTEGER, in_reply_to TEXT,
                    channel_type TEXT, platform_id TEXT,
                    content TEXT
                )
            """)

        self.transport = NanoClawTransport(
            root=root, agent_group_id="group",
            session_id="session", timeout=1,
            poll_interval=0.01,
        )

    def test_empty_prompt_rejected(self):
        with self.assertRaises(ValueError):
            self.transport.request("")

    def test_unavailable_socket(self):
        with self.assertRaisesRegex(
            NanoClawTransportError, "socket unavailable"
        ):
            self.transport.request("diagnose")

    def test_missing_mailbox(self):
        self.inbound.unlink()
        with self.assertRaisesRegex(
            NanoClawTransportError, "Mailbox missing"
        ):
            self.transport._connect_readonly(self.inbound)

    def test_correlated_response(self):
        root = Path(self.temp.name)
        socket_path = root / "data/cli.sock"
        ready = threading.Event()
        errors = []

        def fake_server():
            try:
                with socket.socket(
                    socket.AF_UNIX, socket.SOCK_STREAM
                ) as server:
                    server.bind(str(socket_path))
                    server.listen(1)
                    ready.set()
                    conn, _ = server.accept()
                    with conn:
                        data = b""
                        while b"\n" not in data:
                            chunk = conn.recv(65536)
                            if not chunk:
                                break
                            data += chunk

                    payload = json.loads(data.decode().strip())
                    self.assertEqual(
                        payload["to"]["channelType"], "cli"
                    )
                    inbound_id = "fake-request:group"

                    with sqlite3.connect(self.inbound) as db:
                        db.execute(
                            "INSERT INTO messages_in VALUES (?,?,?,?)",
                            (
                                inbound_id, "cli", "local",
                                json.dumps({"text": payload["text"]}),
                            ),
                        )

                    with sqlite3.connect(self.outbound) as db:
                        db.execute(
                            "INSERT INTO messages_out VALUES (?,?,?,?,?)",
                            (
                                1, inbound_id, "cli", "local",
                                json.dumps({"text": "DIAGNOSIS-OK"}),
                            ),
                        )
            except Exception as exc:
                errors.append(exc)
                ready.set()

        worker = threading.Thread(target=fake_server)
        worker.start()
        self.assertTrue(ready.wait(2))

        try:
            result = self.transport.request("diagnose")
            self.assertEqual(result, "DIAGNOSIS-OK")
        finally:
            worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_inbound_timeout(self):
        with patch("socket.socket") as mocked:
            mocked.return_value.__enter__.return_value.recv.return_value = b""
            with self.assertRaisesRegex(
                NanoClawTransportError,
                "Timed out locating NanoClaw request",
            ):
                self.transport.request("diagnose")


if __name__ == "__main__":
    unittest.main()
