"""
Tests for the LiteLLM client.
"""

import asyncio
import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from broker.config import BrokerConfig
from broker.litellm_client import LiteLLMClient
from broker.protocol import RPCRequest


@pytest.fixture
def mock_config():
    """Create a mock broker configuration."""
    return BrokerConfig(
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


@pytest.fixture
def mock_request():
    """Create a mock RPC request."""
    return RPCRequest(
        request_id="test-123",
        model="fast",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=128,
        temperature=0.5,
    )


@pytest.mark.asyncio
async def test_litellm_client_init(mock_config):
    """Test LiteLLMClient initialization."""
    client = LiteLLMClient(mock_config)
    assert client.config == mock_config
    assert client.session is None


@pytest.mark.asyncio
async def test_litellm_client_context_manager(mock_config):
    """Test LiteLLMClient context manager."""
    async with LiteLLMClient(mock_config) as client:
        assert client.session is not None
        assert not client.session.closed


@pytest.mark.asyncio
async def test_litellm_client_call_litellm_success(mock_config, mock_request):
    """Test successful call to LiteLLM."""
    # Mock aiohttp session with proper async context manager
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "choices": [{
            "message": {
                "content": "Test response"
            }
        }]
    })

    async def chunks(size):
        yield json.dumps(await mock_response.json()).encode()
    mock_response.content.iter_chunked = chunks

    # Create a mock session that properly handles async context manager
    mock_session = MagicMock()

    # Mock the close method to be awaitable
    mock_session.close = AsyncMock()

    # Mock the post method to return a mock response that acts as an async context manager
    mock_post_context_manager = MagicMock()
    mock_post_context_manager.__aenter__.return_value = mock_response
    mock_post_context_manager.__aexit__ = AsyncMock(return_value=None)
    mock_session.post.return_value = mock_post_context_manager

    with patch('broker.litellm_client.aiohttp.ClientSession', return_value=mock_session):
        async with LiteLLMClient(mock_config) as client:
            response = await client.call_litellm(mock_request)

            # Verify the response
            response_data = json.loads(response)
            assert response_data["request_id"] == "test-123"
            assert response_data["ok"] is True
            assert response_data["content"] == "Test response"
            assert response_data["error"] is None

            # Verify the session was called correctly
            mock_session.post.assert_called_once_with(
                "http://litellm:4000/v1/chat/completions",
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 128,
                    "temperature": 0.5,
                },
                timeout=ANY,
                allow_redirects=False,
                headers={
                    "Authorization": "Bearer test_master_key",
                    "Content-Type": "application/json",
                }
            )


@pytest.mark.asyncio
async def test_litellm_client_call_litellm_error(mock_config, mock_request):
    """Test error response from LiteLLM."""
    # Mock aiohttp session with proper async context manager
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="Internal Server Error")

    async def chunks(size):
        yield json.dumps(await mock_response.json()).encode()
    mock_response.content.iter_chunked = chunks

    # Create a mock session that properly handles async context manager
    mock_session = MagicMock()

    # Mock the close method to be awaitable
    mock_session.close = AsyncMock()

    # Mock the post method to return a mock response that acts as an async context manager
    mock_post_context_manager = MagicMock()
    mock_post_context_manager.__aenter__.return_value = mock_response
    mock_post_context_manager.__aexit__ = AsyncMock(return_value=None)
    mock_session.post.return_value = mock_post_context_manager

    with patch('broker.litellm_client.aiohttp.ClientSession', return_value=mock_session):
        async with LiteLLMClient(mock_config) as client:
            response = await client.call_litellm(mock_request)

            # Verify the error response
            response_data = json.loads(response)
            assert response_data["request_id"] == "test-123"
            assert response_data["ok"] is False
            assert response_data["content"] is None
            assert response_data["error"] == "inference backend failed"


@pytest.mark.asyncio
async def test_litellm_client_call_litellm_no_session():
    """Test calling LiteLLM without initialized session."""
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
    # Don't initialize session

    with pytest.raises(RuntimeError, match="LiteLLMClient not initialized"):
        await client.call_litellm(RPCRequest(
            request_id="test-123",
            model="fast",
            messages=[{"role": "user", "content": "Hello"}],
        ))