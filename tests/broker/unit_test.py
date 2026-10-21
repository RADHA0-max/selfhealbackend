#!/usr/bin/env python3
"""
Unit tests for the NanoClaw broker components.
These tests verify the core functionality without requiring actual LiteLLM server.
"""

import json
import pytest
from broker.config import load_config, BrokerConfig
from broker.protocol import parse_request, make_response, RPCRequest
from broker.litellm_client import LiteLLMClient


def test_config_loading():
    """Test that configuration loading works correctly."""
    # Test with minimal environment variables
    import os
    original_key = os.environ.get("LITELLM_MASTER_KEY")
    os.environ["LITELLM_MASTER_KEY"] = "test_key"

    try:
        config = load_config()
        assert config.litellm_master_key == "test_key"
        assert config.litellm_base_url == "http://litellm:4000"
    finally:
        # Restore original environment
        if original_key is not None:
            os.environ["LITELLM_MASTER_KEY"] = original_key
        elif "LITELLM_MASTER_KEY" in os.environ:
            del os.environ["LITELLM_MASTER_KEY"]


def test_protocol_parsing():
    """Test protocol parsing functionality."""
    # Test valid chat request
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


def test_protocol_parsing_embed():
    """Test protocol parsing for embed requests."""
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


def test_protocol_invalid_model():
    """Test protocol parsing with invalid model."""
    request_data = {
        "request_id": "test-123",
        "model": "invalid-model",
        "messages": [{"role": "user", "content": "Hello"}]
    }

    raw_request = json.dumps(request_data).encode("utf-8")

    with pytest.raises(ValueError, match="model is not allowed"):
        parse_request(raw_request)


def test_protocol_invalid_json():
    """Test protocol parsing with invalid JSON."""
    raw_request = b"invalid json {"

    with pytest.raises(ValueError, match="invalid JSON"):
        parse_request(raw_request)


def test_protocol_size_limit():
    """Test protocol size limit enforcement."""
    # Create a request that's too large
    large_data = {
        "request_id": "test-123",
        "model": "fast",
        "messages": [
            {"role": "user", "content": "x" * (65536 + 1)}  # 64KB + 1 byte
        ]
    }

    raw_request = json.dumps(large_data).encode("utf-8")

    with pytest.raises(ValueError, match="request exceeds 64 KiB limit"):
        parse_request(raw_request)


def test_protocol_response_creation():
    """Test response creation functionality."""
    response_bytes = make_response(
        request_id="test-123",
        content="test response"
    )

    response_data = json.loads(response_bytes)
    assert response_data["request_id"] == "test-123"
    assert response_data["ok"] is True
    assert response_data["content"] == "test response"
    assert response_data["error"] is None


def test_protocol_response_error():
    """Test error response creation."""
    response_bytes = make_response(
        request_id="test-123",
        error="test error"
    )

    response_data = json.loads(response_bytes)
    assert response_data["request_id"] == "test-123"
    assert response_data["ok"] is False
    assert response_data["content"] is None
    assert response_data["error"] == "test error"


def test_protocol_response_size_limit():
    """Test response size limit enforcement."""
    # Create a response that's too large
    large_content = "x" * (65536 + 1)  # 64KB + 1 byte

    with pytest.raises(ValueError, match="response exceeds 64 KiB limit"):
        make_response(
            request_id="test-123",
            content=large_content
        )


def test_litellm_client_initialization():
    """Test LiteLLMClient initialization."""
    config = BrokerConfig(
        litellm_base_url="http://litellm:4000",
        litellm_master_key="test_master_key",
        rpc_in_dir="/tmp/in",
        rpc_out_dir="/tmp/out",
        rpc_failed_dir="/tmp/failed",
        max_queue_size=8,
        deep_per_target_per_hour=5,
        coder_per_target_per_hour=3,
        deep_global_per_hour=20,
        max_deep_coder_concurrency=3,
    )

    client = LiteLLMClient(config)
    assert client.config == config
    assert client.session is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])