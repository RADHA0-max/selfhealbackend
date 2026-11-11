"""In-memory RPC test double; never opens network or file-RPC queues."""

from __future__ import annotations

from typing import Any


class OfflineRPC:
    """Return predefined model responses without external I/O."""

    def __init__(self, response: str):
        if not isinstance(response, str):
            raise TypeError("response must be a string")
        self._response = response
        self.calls: list[tuple] = []

    def call(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        self.calls.append(
            (model, messages, {
                "max_tokens": max_tokens,
                "temperature": temperature,
            })
        )
        return {"ok": True, "content": self._response}
