"""In-memory Ollama transport for offline diagnosis integration tests.

This module does not perform network I/O.
"""

import copy
import json
from dataclasses import asdict

from ollama.adapter import OllamaResponseError, parse_diagnosis


class OfflineOllamaTransport:
    """Serve one predefined Ollama response through the diagnosis RPC interface."""

    def __init__(self, response):
        self._response = copy.deepcopy(response)
        self.calls = []

    def call(self, model, messages, *, max_tokens=256, temperature=0.0):
        """Return a validated, RPC-compatible diagnosis response."""

        self.calls.append({
            "model": model,
            "messages": copy.deepcopy(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        })

        if model != "fast":
            raise ValueError("Only the fast diagnosis model is supported")

        if not isinstance(messages, list):
            raise TypeError("Messages must be a list")

        try:
            diagnosis = parse_diagnosis(self._response)
        except OllamaResponseError:
            return {
                "ok": False,
                "content": None,
            }

        return {
            "ok": True,
            "content": json.dumps(asdict(diagnosis)),
        }
