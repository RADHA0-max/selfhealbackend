"""Offline validation adapter for Ollama-style diagnosis responses."""

from agent.diagnosis import DiagnosisError, validate_diagnosis


MAX_RESPONSE_BYTES = 8192


class OllamaResponseError(ValueError):
    """Raised when a model response is invalid."""


def extract_response(payload):
    """Extract bounded response text from an Ollama-style payload."""

    if not isinstance(payload, dict):
        raise OllamaResponseError("Payload must be an object")

    if "error" in payload:
        raise OllamaResponseError("Ollama reported an error")

    if "done" in payload and payload["done"] is not True:
        raise OllamaResponseError("Incomplete Ollama response")

    message = payload.get("message")

    if not isinstance(message, dict):
        raise OllamaResponseError("Missing message object")

    content = message.get("content")

    if not isinstance(content, str):
        raise OllamaResponseError("Message content must be text")

    if len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise OllamaResponseError("Response exceeds size limit")

    return content


def parse_diagnosis(payload):
    """Parse an Ollama-style response without performing network I/O."""

    content = extract_response(payload)

    try:
        return validate_diagnosis(content)
    except DiagnosisError as exc:
        raise OllamaResponseError("Invalid diagnosis output") from exc
