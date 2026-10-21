"""
Unit tests for the NanoClaw RPC client.
"""

import json
import tempfile
import os
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from nanoclaw.rpc_client import RPCClient
from nanoclaw.config import NanoClawConfig


def test_rpc_client_initialization():
    """Test RPC client initialization with default config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)
        assert client.config is not None
        assert hasattr(client.config, 'in_dir')
        assert hasattr(client.config, 'out_dir')
        assert hasattr(client.config, 'failed_dir')


def test_rpc_client_initialization_with_config():
    """Test RPC client initialization with custom config."""
    config = NanoClawConfig(base_dir="/tmp/test_rpc")
    client = RPCClient(config)
    assert client.config == config


def test_generate_request_id():
    """Test request ID generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)
        request_id = client._generate_request_id()
        assert isinstance(request_id, str)
        assert len(request_id) > 0


def test_validate_request_valid():
    """Test valid request validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)
        request = {
            "model": "fast",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ]
        }

        # This should not raise an exception
        client._validate_request(request)


def test_validate_request_invalid_model():
    """Test invalid model validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)
        request = {
            "model": "invalid_model",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ]
        }

        with pytest.raises(ValueError, match="Invalid model backend"):
            client._validate_request(request)


def test_validate_request_missing_model():
    """Test missing model validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)
        request = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ]
        }

        with pytest.raises(ValueError, match="Request must contain 'model' field"):
            client._validate_request(request)


def test_validate_request_missing_messages():
    """Test missing messages validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)
        request = {
            "model": "fast"
        }

        with pytest.raises(ValueError, match="Request must contain 'messages' field"):
            client._validate_request(request)


def test_validate_request_invalid_messages():
    """Test invalid messages validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)
        request = {
            "model": "fast",
            "messages": "not_a_list"
        }

        with pytest.raises(ValueError, match="'messages' must be a list"):
            client._validate_request(request)


def test_write_request_atomically():
    """Test atomic request writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)

        request_id = "test-request-id"
        request = {
            "request_id": request_id,
            "model": "fast",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ]
        }

        # Write request atomically
        file_path = client._write_request_atomically(request_id, request)

        # Check that the file exists
        assert file_path.exists()
        assert file_path.name == f"req-{request_id}.json"

        # Check that the content is correct
        with open(file_path, 'r') as f:
            content = json.load(f)
            assert content["request_id"] == request_id
            assert content["model"] == "fast"
            assert len(content["messages"]) == 2


def test_write_request_atomically_cleanup_on_error():
    """Test cleanup of temporary files on error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)

        # Mock os.rename to raise an exception
        with patch('os.rename') as mock_rename:
            mock_rename.side_effect = Exception("Test error")

            request_id = "test-request-id"
            request = {
                "request_id": request_id,
                "model": "fast",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello!"}
                ]
            }

            # This should raise an exception
            with pytest.raises(Exception):
                client._write_request_atomically(request_id, request)

            # Check that no temporary files remain
            in_dir = Path(tmpdir) / "in"
            files = list(in_dir.glob("req-*"))
            assert len(files) == 0


def test_wait_for_response_success():
    """Test successful response waiting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)

        request_id = "test-request-id"
        response = {
            "request_id": request_id,
            "model": "fast",
            "response": "Hello, world!"
        }

        # Create response file
        response_file = config.out_dir / f"resp-{request_id}.json"
        with open(response_file, 'w') as f:
            json.dump(response, f)

        # Wait for response
        result = client._wait_for_response(request_id)

        # Check that response is returned correctly
        assert result["request_id"] == request_id
        assert result["response"] == "Hello, world!"

        # Check that response file was deleted
        assert not response_file.exists()


def test_wait_for_response_timeout():
    """Test timeout when no response is received."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories and short timeout
        config = NanoClawConfig(base_dir=tmpdir)
        config.rpc_timeout = 0.1  # 100ms timeout
        client = RPCClient(config)

        request_id = "test-request-id"

        # Wait for response (should timeout)
        with pytest.raises(TimeoutError):
            client._wait_for_response(request_id)


def test_wait_for_response_malformed():
    """Test handling of malformed response."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)

        request_id = "test-request-id"

        # Create malformed response file
        response_file = config.out_dir / f"resp-{request_id}.json"
        with open(response_file, 'w') as f:
            f.write("not a json")

        # Wait for response (should raise ValueError)
        with pytest.raises(ValueError, match="Malformed response"):
            client._wait_for_response(request_id)

        # Check that malformed file was moved to failed directory
        failed_file = config.failed_dir / f"resp-{request_id}.json"
        assert failed_file.exists()


def test_make_request():
    """Test full make_request functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)

        request_id = "test-request-id"
        request = {
            "request_id": request_id,
            "model": "fast",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ]
        }

        # Mock the response
        response = {
            "request_id": request_id,
            "model": "fast",
            "response": "Hello, world!"
        }

        # Create response file
        response_file = config.out_dir / f"resp-{request_id}.json"
        with open(response_file, 'w') as f:
            json.dump(response, f)

        # Make request (this will create the request file and then read the response)
        # We'll mock the file creation to avoid actual file system operations
        with patch.object(client, '_write_request_atomically') as mock_write:
            with patch.object(client, '_wait_for_response') as mock_wait:
                mock_write.return_value = Path(tmpdir) / "req-test-request-id.json"
                mock_wait.return_value = response

                result = client.make_request("fast", request["messages"])

                # Check that the response is returned correctly
                assert result["response"] == "Hello, world!"


def test_make_request_sync():
    """Test make_request_sync functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config with temp directories
        config = NanoClawConfig(base_dir=tmpdir)
        client = RPCClient(config)

        request_id = "test-request-id"
        request = {
            "request_id": request_id,
            "model": "fast",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ]
        }

        # Mock the response
        response = {
            "request_id": request_id,
            "model": "fast",
            "response": "Hello, world!"
        }

        # Create response file
        response_file = config.out_dir / f"resp-{request_id}.json"
        with open(response_file, 'w') as f:
            json.dump(response, f)

        # Make request (this will create the request file and then read the response)
        # We'll mock the file creation to avoid actual file system operations
        with patch.object(client, '_write_request_atomically') as mock_write:
            with patch.object(client, '_wait_for_response') as mock_wait:
                mock_write.return_value = Path(tmpdir) / "req-test-request-id.json"
                mock_wait.return_value = response

                result = client.make_request_sync("fast", request["messages"])

                # Check that the response is returned correctly
                assert result["response"] == "Hello, world!"