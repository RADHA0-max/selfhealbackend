from __future__ import annotations

"""Person 2: NanoClaw agent transport through CLI and correlated SQLite mailboxes."""

import json
import socket
import sqlite3
import time
import uuid
from pathlib import Path


class NanoClawTransportError(RuntimeError):
    pass


class NanoClawTransport:
    def __init__(
        self,
        root: str | Path,
        agent_group_id: str,
        session_id: str,
        timeout: float = 120.0,
        poll_interval: float = 0.2,
    ):
        self.root = Path(root)
        self.agent_group_id = agent_group_id
        self.session_id = session_id
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.socket_path = self.root / "data" / "cli.sock"
        mailbox = (
            self.root / "data" / "v2-sessions"
            / agent_group_id / session_id
        )
        self.inbound = mailbox / "inbound.db"
        self.outbound = mailbox / "outbound.db"

    @staticmethod
    def _connect_readonly(path: Path):
        if not path.is_file():
            raise NanoClawTransportError(f"Mailbox missing: {path}")
        return sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=2,
        )

    def request(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("Prompt must be a nonempty string")

        marker = f"P2-{uuid.uuid4().hex}"
        tagged_prompt = f"[BENCH_REQUEST_ID:{marker}]\n{prompt}"
        deadline = time.monotonic() + self.timeout

        # Routed CLI submission does not claim or evict the interactive chat slot.
        payload = {
            "text": tagged_prompt,
            "to": {
                "channelType": "cli",
                "platformId": "local",
                "instance": "cli",
                "threadId": None,
            },
        }

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(min(5.0, self.timeout))
                conn.connect(str(self.socket_path))
                conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                # Keep the connection alive briefly so the server can read
                # the complete request; responses are read from SQLite.
                conn.shutdown(socket.SHUT_WR)
                conn.settimeout(0.5)
                try:
                    conn.recv(4096)
                except (socket.timeout, ConnectionResetError):
                    pass
        except OSError as exc:
            raise NanoClawTransportError(
                f"NanoClaw CLI socket unavailable: {exc}"
            ) from exc

        inbound_id = None

        while time.monotonic() < deadline:
            try:
                with self._connect_readonly(self.inbound) as db:
                    matches = db.execute(
                        """
                        SELECT id FROM messages_in
                        WHERE channel_type = 'cli'
                          AND platform_id = 'local'
                          AND instr(content, ?) > 0
                        """,
                        (marker,),
                    ).fetchall()
                if len(matches) > 1:
                    raise NanoClawTransportError(
                        "Ambiguous inbound request correlation"
                    )
                if matches:
                    inbound_id = matches[0][0]
                    break
            except sqlite3.Error as exc:
                raise NanoClawTransportError(
                    f"Inbound mailbox error: {exc}"
                ) from exc
            time.sleep(self.poll_interval)

        if inbound_id is None:
            raise NanoClawTransportError(
                f"Timed out locating NanoClaw request {marker}"
            )

        last_change = None
        previous_rows = None

        while time.monotonic() < deadline:
            try:
                with self._connect_readonly(self.outbound) as db:
                    rows = db.execute(
                        """
                        SELECT content FROM messages_out
                        WHERE in_reply_to = ?
                          AND channel_type = 'cli'
                          AND platform_id = 'local'
                        ORDER BY seq ASC
                        """,
                        (inbound_id,),
                    ).fetchall()
            except sqlite3.Error as exc:
                raise NanoClawTransportError(
                    f"Outbound mailbox error: {exc}"
                ) from exc

            if rows:
                if rows != previous_rows:
                    previous_rows = rows
                    last_change = time.monotonic()
                if time.monotonic() - last_change < 0.5:
                    time.sleep(self.poll_interval)
                    continue

                texts = []
                for (raw,) in rows:
                    try:
                        content = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise NanoClawTransportError(
                            "Malformed outbound message JSON"
                        ) from exc
                    if isinstance(content, dict) and isinstance(
                        content.get("text"), str
                    ):
                        texts.append(content["text"])
                if texts:
                    return "\n".join(texts)

            time.sleep(self.poll_interval)

        raise NanoClawTransportError(
            f"Timed out waiting for correlated NanoClaw reply {marker}"
        )
