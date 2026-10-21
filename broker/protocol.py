from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import uuid
import re


MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024


ALLOWED_MODELS = {
    "fast",
    "plan",
    "deep",
    "coder",
    "embed",
}


@dataclass(frozen=True)
class RPCRequest:
    request_id: str
    model: str
    messages: list[dict[str, Any]] | None = None
    input: str | list[str] | None = None
    max_tokens: int = 256
    temperature: float = 0.0


@dataclass(frozen=True)
class RPCResponse:
    request_id: str
    ok: bool
    content: str | None = None
    embedding: list[float] | None = None
    error: str | None = None


def new_request_id() -> str:
    return uuid.uuid4().hex


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def parse_request(raw: bytes) -> RPCRequest:
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds 64 KiB limit")

    try:
        data = json.loads(raw, object_pairs_hook=unique_fields)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("request must be a JSON object")

    allowed_fields = {
        "request_id", "model", "messages", "input",
        "max_tokens", "temperature",
    }
    unknown_fields = set(data) - allowed_fields
    if unknown_fields:
        raise ValueError(
            "unknown request fields: " + ", ".join(sorted(unknown_fields))
        )

    request_id = data.get("request_id")
    model = data.get("model")

    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", request_id):
        raise ValueError("request_id must be a non-empty string")

    if not isinstance(model, str) or model not in ALLOWED_MODELS:
        raise ValueError("model is not allowed")

    messages = data.get("messages")
    input_value = data.get("input")

    if model == "embed":
        if not isinstance(input_value, (str, list)):
            raise ValueError("embed requires string or list input")
        if isinstance(input_value, list) and (not input_value or any(not isinstance(x, str) for x in input_value)):
            raise ValueError("embed list must contain strings")
        messages = None
    else:
        if not isinstance(messages, list) or not messages:
            raise ValueError("chat model requires non-empty messages")
        input_value = None

    max_tokens = data.get("max_tokens", 256)
    temperature = data.get("temperature", 0.0)

    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
        raise ValueError("max_tokens must be a positive integer")

    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ValueError("temperature must be numeric")
    import math
    if not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise ValueError("temperature must be finite and between 0 and 2")

    if model != "embed":
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ValueError(f"messages[{index}] must be an object")
            if not isinstance(message.get("role"), str) or not message["role"]:
                raise ValueError(f"messages[{index}].role must be a non-empty string")

    return RPCRequest(
        request_id=request_id,
        model=model,
        messages=messages,
        input=input_value,
        max_tokens=max_tokens,
        temperature=float(temperature),
    )


def make_response(
    request_id: str,
    *,
    content: str | None = None,
    embedding: list[float] | None = None,
    error: str | None = None,
) -> bytes:
    response = RPCResponse(
        request_id=request_id,
        ok=error is None,
        content=content,
        embedding=embedding,
        error=error,
    )

    payload = json.dumps(
        {
            "request_id": response.request_id,
            "ok": response.ok,
            "content": response.content,
            "embedding": response.embedding,
            "error": response.error,
        },
        separators=(",", ":"),
    ).encode("utf-8")

    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("response exceeds 64 KiB limit")

    return payload
