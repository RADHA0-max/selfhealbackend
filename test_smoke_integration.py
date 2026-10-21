#!/usr/bin/env python3
"""
Smoke test for NanoClaw broker integration with LiteLLM/Qwen inference.
This test verifies that the broker can properly communicate with LiteLLM
and return responses containing FOUNDATION_OK.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

from broker.config import load_config
from broker.protocol import RPCRequest, make_response, new_request_id
from broker.litellm_client import LiteLLMClient


async def test_broker_integration():
    """Test the broker integration with LiteLLM."""

    # Load configuration
    config = load_config()

    # Create temporary directories for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        rpc_in_dir = temp_path / "in"
        rpc_out_dir = temp_path / "out"
        rpc_failed_dir = temp_path / "failed"

        # Create directories
        rpc_in_dir.mkdir()
        rpc_out_dir.mkdir()
        rpc_failed_dir.mkdir()

        # Update config to use temporary directories
        config.rpc_in_dir = str(rpc_in_dir)
        config.rpc_out_dir = str(rpc_out_dir)
        config.rpc_failed_dir = str(rpc_failed_dir)

        # Create a test request
        request_id = new_request_id()
        test_request = RPCRequest(
            request_id=request_id,
            model="fast",
            messages=[{"role": "user", "content": "Reply exactly with FOUNDATION_OK"}],
            max_tokens=256,
            temperature=0.0
        )

        # Write the request to the input directory
        request_file = rpc_in_dir / f"req-{request_id}.json"
        request_file.write_bytes(json.dumps({
            "request_id": test_request.request_id,
            "model": test_request.model,
            "messages": test_request.messages,
            "max_tokens": test_request.max_tokens,
            "temperature": test_request.temperature
        }).encode('utf-8'))

        print(f"Created test request: {request_file}")
        print(f"Request content: {test_request}")

        # Test the LiteLLM client directly first
        print("Testing LiteLLM client directly...")
        async with LiteLLMClient(config) as client:
            try:
                response_bytes = await client.call_litellm(test_request)
                response_data = json.loads(response_bytes)
                print(f"Direct LiteLLM response: {response_data}")

                if response_data.get('ok') and 'FOUNDATION_OK' in response_data.get('content', ''):
                    print("✓ Direct LiteLLM test passed")
                else:
                    print("✗ Direct LiteLLM test failed")

            except Exception as e:
                print(f"Direct LiteLLM test failed with error: {e}")

        # Now test the broker's actual integration
        print("\nTesting broker integration...")

        # We'll create a minimal broker instance and test the actual _process_request_with_litellm method
        # But we need to make sure it uses the real implementation, not the placeholder

        # For now, let's just test that the broker can process a request properly
        # by directly calling the real implementation

        # Create a simple test to verify the broker can process requests
        from broker.main import Broker

        broker = Broker()
        broker.config = config
        broker.litellm_client = LiteLLMClient(config)

        # Process the request
        try:
            # Process all pending requests
            await broker._process_requests()

            # Check if response was created
            response_file = rpc_out_dir / f"resp-{request_id}.json"
            if response_file.exists():
                response_content = response_file.read_text()
                response_data = json.loads(response_content)
                print(f"Broker response: {response_data}")

                if response_data.get('ok') and 'FOUNDATION_OK' in response_data.get('content', ''):
                    print("✓ Broker integration test passed")
                    return True
                else:
                    print("✗ Broker integration test failed - response doesn't contain FOUNDATION_OK")
                    return False
            else:
                print("✗ Broker integration test failed - no response file created")
                return False

        except Exception as e:
            print(f"Broker integration test failed with error: {e}")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_broker_integration())
    if result:
        print("\n🎉 Smoke test passed!")
    else:
        print("\n❌ Smoke test failed!")
        exit(1)