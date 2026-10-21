"""
Tests for the broker protocol module.
"""

import json
import pytest
from broker.protocol import (
    RPCRequest,
    RPCResponse,
    parse_request,
    make_response,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
)


def test_parse_request_valid_chat():
    """Test parsing a valid chat request."""
    request_data = {
        "request_id": "test-123",
        "model": "fast",
        "messages": [
            {"role": "user", "content": "Hello"}
        ],
        "max_tokens": 128,
        "temperature": 0.5
    }

    raw_request = json.dumps(request_data).encode("utf-8")
    request = parse_request(raw_request)

    assert request.request_id == "test-123"
    assert request.model == "fast"
    assert request.messages == [{"role": "user", "content": "Hello"}]
    assert request.max_tokens == 128
    assert request.temperature == 0.5


def test_parse_request_valid_embed():
    """Test parsing a valid embed request."""
    request_data = {
        "request_id": "test-456",
        "model": "embed",
        "input": "test input",
        "max_tokens": 128,
        "temperature": 0.5
    }

    raw_request = json.dumps(request_data).encode("utf-8")
    request = parse_request(raw_request)

    assert request.request_id == "test-456"
    assert request.model == "embed"
    assert request.input == "test input"
    assert request.max_tokens == 128
    assert request.temperature == 0.5


def test_parse_request_invalid_model():
    """Test parsing a request with invalid model."""
    request_data = {
        "request_id": "test-123",
        "model": "invalid-model",
        "messages": [{"role": "user", "content": "Hello"}]
    }

    raw_request = json.dumps(request_data).encode("utf-8")

    with pytest.raises(ValueError, match="model is not allowed"):
        parse_request(raw_request)


def test_parse_request_invalid_json():
    """Test parsing invalid JSON."""
    raw_request = b"invalid json {"

    with pytest.raises(ValueError, match="invalid JSON"):
        parse_request(raw_request)


def test_parse_request_exceeds_limit():
    """Test parsing a request that exceeds the size limit."""
    # Create a request that's too large
    large_data = {
        "request_id": "test-123",
        "model": "fast",
        "messages": [
            {"role": "user", "content": "x" * (MAX_REQUEST_BYTES + 1)}
        ]
    }

    raw_request = json.dumps(large_data).encode("utf-8")

    with pytest.raises(ValueError, match="request exceeds 64 KiB limit"):
        parse_request(raw_request)


def test_make_response_success():
    """Test creating a successful response."""
    response_bytes = make_response(
        request_id="test-123",
        content="test response"
    )

    response_data = json.loads(response_bytes)
    assert response_data["request_id"] == "test-123"
    assert response_data["ok"] is True
    assert response_data["content"] == "test response"
    assert response_data["error"] is None


def test_make_response_error():
    """Test creating an error response."""
    response_bytes = make_response(
        request_id="test-123",
        error="test error"
    )

    response_data = json.loads(response_bytes)
    assert response_data["request_id"] == "test-123"
    assert response_data["ok"] is False
    assert response_data["content"] is None
    assert response_data["error"] == "test error"


def test_make_response_exceeds_limit():
    """Test creating a response that exceeds the size limit."""
    # Create a response that's too large
    large_content = "x" * (MAX_RESPONSE_BYTES + 1)

    with pytest.raises(ValueError, match="response exceeds 64 KiB limit"):
        make_response(
            request_id="test-123",
            content=large_content
        )