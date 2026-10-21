#!/usr/bin/env python3
"""
Integration test for the NanoClaw foundation sprint.

This test verifies that the file-based LLM RPC system works correctly
with the actual LiteLLM inference gateway.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

from broker.config import load_config
from broker.litellm_client import LiteLLMClient
from broker.protocol import parse_request, make_response


async def test_foundation_sprint_integration():
    """Test the foundation sprint integration with real LiteLLM."""
    print("Testing foundation sprint integration...")

    # Load configuration
    config = load_config()
    print(f"Using LiteLLM base URL: {config.litellm_base_url}")

    # Create a test request that matches the requirements
    test_request_data = {
        "request_id": "foundation-test-123",
        "model": "fast",
        "messages": [
            {"role": "user", "content": "Reply exactly with FOUNDATION_OK"}
        ],
        "max_tokens": 128,
        "temperature": 0.0
    }

    # Create a temporary directory structure for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        in_dir = Path(tmpdir) / "in"
        out_dir = Path(tmpdir) / "out"
        failed_dir = Path(tmpdir) / "failed"

        in_dir.mkdir()
        out_dir.mkdir()
        failed_dir.mkdir()

        # Update config to use temporary directories
        test_config = type(config)(
            litellm_base_url=config.litellm_base_url,
            litellm_master_key=config.litellm_master_key,
            rpc_in_dir=str(in_dir),
            rpc_out_dir=str(out_dir),
            rpc_failed_dir=str(failed_dir),
            max_queue_size=config.max_queue_size,
            deep_per_target_per_hour=config.deep_per_target_per_hour,
            coder_per_target_per_hour=config.coder_per_target_per_hour,
            deep_global_per_hour=config.deep_global_per_hour,
            max_deep_coder_concurrency=config.max_deep_coder_concurrency,
        )

        # Write the test request to the input directory
        request_file = in_dir / "req-foundation-test-123.json"
        request_file.write_text(json.dumps(test_request_data))

        print("Created test request file")

        # Test the LiteLLM client directly
        async with LiteLLMClient(test_config) as client:
            # Parse the request
            raw_request = request_file.read_bytes()
            request = parse_request(raw_request)

            # Call LiteLLM
            response = await client.call_litellm(request)

            # Parse the response
            response_data = json.loads(response)

            print(f"Response received: {response_data}")

            # Verify the response
            assert response_data["request_id"] == "foundation-test-123"
            assert response_data["ok"] is True
            assert response_data["content"] is not None
            assert "FOUNDATION_OK" in response_data["content"]

            print("✅ Foundation sprint integration test passed!")
            return True


if __name__ == "__main__":
    # Run the integration test
    try:
        result = asyncio.run(test_foundation_sprint_integration())
        if result:
            print("SUCCESS: Foundation sprint implementation is working correctly")
        else:
            print("FAILURE: Foundation sprint implementation failed")
            exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)