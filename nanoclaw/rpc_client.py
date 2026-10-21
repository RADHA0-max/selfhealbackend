"""
NanoClaw RPC Client

File-based RPC client for communicating with the trusted broker.
"""

import json
import time
import uuid
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from .config import NanoClawConfig


class RPCClient:
    """RPC client for NanoClaw to communicate with the trusted broker."""

    def __init__(self, config: Optional[NanoClawConfig] = None):
        """
        Initialize the RPC client.

        Args:
            config: NanoClaw configuration instance
        """
        self.config = config or NanoClawConfig()

    def _generate_request_id(self) -> str:
        """
        Generate a unique request ID.

        Returns:
            Unique request ID string
        """
        return str(uuid.uuid4())

    def _validate_request(self, request: Dict[str, Any]) -> None:
        """
        Validate the request locally before writing to file.

        Args:
            request: Request dictionary to validate

        Raises:
            ValueError: If request is invalid
        """
        if not isinstance(request, dict):
            raise ValueError("Request must be a dictionary")

        # Check required fields
        if "model" not in request:
            raise ValueError("Request must contain 'model' field")

        model = request["model"]
        if not isinstance(model, str):
            raise ValueError("'model' must be a string")

        # Validate model backend
        if not self.config.validate_backend(model):
            raise ValueError(f"Invalid model backend: {model}")

        # Check that request size is within limits
        request_json = json.dumps(request)
        if len(request_json.encode('utf-8')) > self.config.max_request_size:
            raise ValueError("Request exceeds maximum size limit")

        # Check for required fields based on model type
        if "messages" not in request:
            raise ValueError("Request must contain 'messages' field")

        if not isinstance(request["messages"], list):
            raise ValueError("'messages' must be a list")

    def _write_request_atomically(self, request_id: str, request: Dict[str, Any]) -> Path:
        """
        Write request file atomically to prevent partial writes.

        Args:
            request_id: Unique request ID
            request: Request dictionary

        Returns:
            Path to the written request file
        """
        # Create temporary file in the same directory for atomic rename
        request_file = self.config.in_dir / f"req-{request_id}.json"

        # Write to temporary file first
        temp_file = self.config.in_dir / f"req-{request_id}.tmp"

        try:
            # Write to temporary file
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(request, f, ensure_ascii=False, indent=2)

            # Atomic rename to final file
            os.rename(temp_file, request_file)

            return request_file
        except Exception:
            # Clean up temporary file if something goes wrong
            if temp_file.exists():
                temp_file.unlink()
            raise

    def _wait_for_response(self, request_id: str) -> Dict[str, Any]:
        """
        Wait for the corresponding response file.

        Args:
            request_id: Request ID to wait for

        Returns:
            Response dictionary

        Raises:
            TimeoutError: If response is not received within timeout
            ValueError: If response is malformed
        """
        response_file = self.config.out_dir / f"resp-{request_id}.json"
        start_time = time.time()

        while time.time() - start_time < self.config.rpc_timeout:
            if response_file.exists():
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response = json.load(f)

                    # Validate response structure
                    if not isinstance(response, dict):
                        raise ValueError("Response must be a dictionary")

                    # Remove the response file after reading
                    response_file.unlink()
                    return response
                except (json.JSONDecodeError, ValueError) as e:
                    # If response is malformed, move it to failed directory
                    failed_file = self.config.failed_dir / f"resp-{request_id}.json"
                    try:
                        os.rename(response_file, failed_file)
                    except Exception:
                        pass  # Ignore if we can't move it
                    raise ValueError(f"Malformed response: {str(e)}")

            # Wait a bit before checking again
            time.sleep(0.1)

        # Timeout reached
        raise TimeoutError(f"Response not received for request {request_id} within {self.config.rpc_timeout} seconds")

    def make_request(self, model: str, messages: list, **kwargs) -> Dict[str, Any]:
        """
        Make an RPC request to the broker.

        Args:
            model: Model alias (fast, plan, deep, coder, embed)
            messages: List of messages for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker

        Raises:
            ValueError: If request is invalid
            TimeoutError: If response times out
            Exception: If response is malformed or other errors occur
        """
        # Generate unique request ID
        request_id = self._generate_request_id()

        # Build request
        request = {
            "request_id": request_id,
            "model": model,
            "messages": messages,
            **kwargs
        }

        # Validate request
        self._validate_request(request)

        try:
            # Write request atomically
            self._write_request_atomically(request_id, request)

            # Wait for response
            response = self._wait_for_response(request_id)

            return response

        except Exception:
            # If there's an error, clean up any temporary files
            # Note: The atomic write should have completed, so we don't need to clean up
            raise

    def make_request_sync(self, model: str, messages: list, **kwargs) -> Dict[str, Any]:
        """
        Synchronous version of make_request for compatibility.

        Args:
            model: Model alias (fast, plan, deep, coder, embed)
            messages: List of messages for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        return self.make_request(model, messages, **kwargs)