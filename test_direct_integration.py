#!/usr/bin/env python3
"""
Simple smoke test for NanoClaw broker integration with LiteLLM/Qwen inference.
This test directly verifies the integration works by using the real LiteLLMClient
and checking if we get FOUNDATION_OK in the response.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

from broker.config import load_config
from broker.protocol import RPCRequest, new_request_id
from broker.litellm_client import LiteLLMClient


async def test_direct_integration():
    """Test the direct integration with LiteLLM using the real client."""

    # Load configuration
    config = load_config()

    # Create a test request
    request_id = new_request_id()
    test_request = RPCRequest(
        request_id=request_id,
        model="fast",
        messages=[{"role": "user", "content": "Reply exactly with FOUNDATION_OK"}],
        max_tokens=256,
        temperature=0.0
    )

    print(f"Testing request: {test_request}")

    # Test the LiteLLM client directly
    print("Testing LiteLLM client directly...")
    async with LiteLLMClient(config) as client:
        try:
            response_bytes = await client.call_litellm(test_request)
            response_data = json.loads(response_bytes)
            print(f"Direct LiteLLM response: {response_data}")

            if response_data.get('ok') and 'FOUNDATION_OK' in response_data.get('content', ''):
                print("✓ Direct LiteLLM test passed - FOUNDATION_OK found in response")
                return True
            else:
                print("✗ Direct LiteLLM test failed - FOUNDATION_OK not found in response")
                return False

        except Exception as e:
            print(f"Direct LiteLLM test failed with error: {e}")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_direct_integration())
    if result:
        print("\n🎉 Direct integration test passed!")
    else:
        print("\n❌ Direct integration test failed!")
        exit(1)