"""Bounded, offline-compatible NanoClaw file-RPC client."""

from __future__ import annotations

import json
import math
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any

from broker.protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    parse_request,
)


class RPCError(Exception):
    """Invalid or failed RPC response."""


class RPCTimeout(RPCError):
    """Request outcome is unknown; do not retry automatically."""


class RPCClient:
    def __init__(
        self,
        in_dir: str | Path,
        out_dir: str | Path,
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> None:

        if not 0 < timeout <= 120:
            raise ValueError(
                "timeout must be between 0 and 120 seconds"
            )

        if not 0 < poll_interval <= 1:
            raise ValueError(
                "poll_interval must be between 0 and 1 second"
            )

        self.in_dir = Path(in_dir)
        self.out_dir = Path(out_dir)
        self.timeout = timeout
        self.poll_interval = poll_interval

        for directory in (self.in_dir, self.out_dir):
            if not directory.is_dir():
                raise ValueError(
                    f"RPC directory does not exist: {directory}"
                )

    def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict[str, Any]:

        request_id = uuid.uuid4().hex

        request = {
            "request_id": request_id,
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        payload = json.dumps(
            request,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

        # Enforce the broker's request-size limit.
        if len(payload) > MAX_REQUEST_BYTES:
            raise ValueError(
                "RPC request exceeds 64 KiB"
            )

        # Validate against the existing broker protocol.
        parse_request(payload)

        request_path = (
            self.in_dir / f"req-{request_id}.json"
        )

        response_path = (
            self.out_dir / f"resp-{request_id}.json"
        )

        temporary_path = (
            self.in_dir / f".tmp-{request_id}"
        )

        # Write the request to a temporary file first.
        fd = os.open(
            temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )

        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

            # Publish the complete request atomically.
            os.replace(
                temporary_path,
                request_path,
            )

            # Persist the directory update.
            directory_fd = os.open(
                self.in_dir,
                os.O_RDONLY | os.O_DIRECTORY,
            )

            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        finally:
            temporary_path.unlink(missing_ok=True)

        deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:

            try:
                fd = os.open(
                    response_path,
                    os.O_RDONLY
                    | os.O_NOFOLLOW
                    | os.O_NONBLOCK,
                )

            except FileNotFoundError:
                time.sleep(self.poll_interval)
                continue

            try:
                metadata = os.fstat(fd)

                if not stat.S_ISREG(metadata.st_mode):
                    raise RPCError(
                        "response is not a regular file"
                    )

                if metadata.st_size > MAX_RESPONSE_BYTES:
                    raise RPCError(
                        "response exceeds 64 KiB"
                    )

                with os.fdopen(fd, "rb") as stream:
                    fd = -1
                    raw = stream.read(
                        MAX_RESPONSE_BYTES + 1
                    )

            finally:
                if fd >= 0:
                    os.close(fd)

            if len(raw) > MAX_RESPONSE_BYTES:
                raise RPCError(
                    "response exceeds 64 KiB"
                )

            # Reject duplicate JSON fields.
            def reject_duplicates(pairs):
                result = {}

                for key, value in pairs:
                    if key in result:
                        raise RPCError(
                            "duplicate response field"
                        )

                    result[key] = value

                return result

            try:
                response = json.loads(
                    raw,
                    object_pairs_hook=reject_duplicates,
                )

            except (ValueError, UnicodeDecodeError) as exc:
                raise RPCError(
                    "invalid response JSON"
                ) from exc

            if not isinstance(response, dict):
                raise RPCError(
                    "response must be an object"
                )

            expected_fields = {
                "request_id",
                "ok",
                "content",
                "embedding",
                "error",
            }

            if set(response) != expected_fields:
                raise RPCError(
                    "unexpected response fields"
                )

            if response["request_id"] != request_id:
                raise RPCError(
                    "response request_id mismatch"
                )

            if type(response["ok"]) is not bool:
                raise RPCError(
                    "response ok must be boolean"
                )

            # Validate text content.
            if (
                response["content"] is not None
                and not isinstance(
                    response["content"],
                    str,
                )
            ):
                raise RPCError(
                    "invalid response content"
                )

            # Validate embedding values.
            if response["embedding"] is not None:

                if not isinstance(
                    response["embedding"],
                    list,
                ):
                    raise RPCError(
                        "invalid response embedding"
                    )

                # SECURITY FIX 1:
                # Reject booleans, NaN, infinity,
                # and other non-finite embedding values.
                if any(
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    for value in response["embedding"]
                ):
                    raise RPCError(
                        "invalid embedding values"
                    )

            # Validate the error field.
            if (
                response["error"] is not None
                and not isinstance(
                    response["error"],
                    str,
                )
            ):
                raise RPCError(
                    "invalid response error"
                )

            # SECURITY FIX 2:
            # A successful response cannot contain an error.
            if (
                response["ok"]
                and response["error"] is not None
            ):
                raise RPCError(
                    "successful response cannot contain an error"
                )

            # Handle broker-reported failures.
            if not response["ok"]:
                raise RPCError(
                    response["error"]
                    or "broker request failed"
                )

            return response

        raise RPCTimeout(
            f"RPC request {request_id} timed out; "
            "outcome is unknown and must not be "
            "retried automatically"
        )
