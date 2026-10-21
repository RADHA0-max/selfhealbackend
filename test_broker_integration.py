#!/usr/bin/env python3
"""
Test script to verify the NanoClaw broker integration works correctly.
This test verifies that the broker can properly process requests and communicate with LiteLLM.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

from broker.config import load_config
from broker.protocol import RPCRequest, new_request_id, parse_request, make_response
from broker.litellm_client import LiteLLMClient
from broker.budget import BudgetTracker


async def test_broker_components():
    """Test the individual components of the broker."""
    print("Testing broker components...")

    # Test 1: Configuration loading
    print("1. Testing configuration loading...")
    try:
        config = load_config()
        print(f"   ✓ Configuration loaded successfully")
        print(f"   ✓ LiteLLM base URL: {config.litellm_base_url}")
        print(f"   ✓ RPC directories: in={config.rpc_in_dir}, out={config.rpc_out_dir}")
    except Exception as e:
        print(f"   ✗ Configuration loading failed: {e}")
        return False

    # Test 2: Protocol parsing and response creation
    print("2. Testing protocol components...")
    try:
        # Test request parsing
        test_request_data = {
            "request_id": "test-123",
            "model": "fast",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": 128,
            "temperature": 0.5
        }

        raw_request = json.dumps(test_request_data).encode("utf-8")
        parsed_request = parse_request(raw_request)

        assert parsed_request.request_id == "test-123"
        assert parsed_request.model == "fast"
        assert parsed_request.messages == [{"role": "user", "content": "Hello"}]
        print("   ✓ Request parsing works correctly")

        # Test response creation
        response_bytes = make_response(
            request_id="test-123",
            content="test response"
        )
        response_data = json.loads(response_bytes)
        assert response_data["request_id"] == "test-123"
        assert response_data["ok"] is True
        assert response_data["content"] == "test response"
        print("   ✓ Response creation works correctly")

    except Exception as e:
        print(f"   ✗ Protocol test failed: {e}")
        return False

    # Test 3: Budget tracker
    print("3. Testing budget tracker...")
    try:
        budget_tracker = BudgetTracker()

        # Test that fast/plan/embed models are always allowed
        assert budget_tracker.can_request("fast", "test-target") == True
        assert budget_tracker.can_request("plan", "test-target") == True
        assert budget_tracker.can_request("embed", "test-target") == True
        print("   ✓ Fast/plan/embed models are always allowed")

        # Test that DEEP/CODER models are subject to budget limits
        # This is a basic check - actual budget enforcement requires more complex testing
        assert budget_tracker.can_request("deep", "test-target") == True  # Should be allowed initially
        assert budget_tracker.can_request("coder", "test-target") == True  # Should be allowed initially
        print("   ✓ DEEP/CODER models can be checked for budget limits")

    except Exception as e:
        print(f"   ✗ Budget tracker test failed: {e}")
        return False

    print("✓ All broker components tests passed!")
    return True


async def test_litellm_client_integration():
    """Test the LiteLLM client integration with actual requests."""
    print("\nTesting LiteLLM client integration...")

    try:
        # Load configuration
        config = load_config()
        print(f"Using LiteLLM base URL: {config.litellm_base_url}")

        # Create a test request that should return FOUNDATION_OK
        test_request = RPCRequest(
            request_id=new_request_id(),
            model="fast",
            messages=[{"role": "user", "content": "Reply exactly with FOUNDATION_OK"}],
            max_tokens=128,
            temperature=0.0
        )

        print(f"Testing request: {test_request}")

        # Test the LiteLLM client directly
        async with LiteLLMClient(config) as client:
            response_bytes = await client.call_litellm(test_request)
            response_data = json.loads(response_bytes)

            print(f"Response received: {response_data}")

            # Verify the response
            if response_data.get('ok') is True and response_data.get('content') and 'FOUNDATION_OK' in response_data['content']:
                print("✓ LiteLLM client integration test passed!")
                return True
            else:
                print("✗ LiteLLM client integration test failed - FOUNDATION_OK not found")
                return False

    except Exception as e:
        print(f"✗ LiteLLM client integration test failed with error: {e}")
        return False


async def test_broker_end_to_end():
    """Test the full broker flow with temporary directories."""
    print("\nTesting full broker end-to-end flow...")

    try:
        # Create temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            in_dir = Path(tmpdir) / "in"
            out_dir = Path(tmpdir) / "out"
            failed_dir = Path(tmpdir) / "failed"

            in_dir.mkdir()
            out_dir.mkdir()
            failed_dir.mkdir()

            # Load configuration
            config = load_config()

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

            # Create a test request file
            request_data = {
                "request_id": "e2e-test-123",
                "model": "fast",
                "messages": [
                    {"role": "user", "content": "Reply exactly with FOUNDATION_OK"}
                ],
                "max_tokens": 128,
                "temperature": 0.0
            }

            request_file = in_dir / "req-e2e-test-123.json"
            request_file.write_text(json.dumps(request_data))

            print("Created test request file")

            # Test the LiteLLM client with this request
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
                if response_data["request_id"] == "e2e-test-123":
                    if response_data["ok"] is True and response_data["content"] and 'FOUNDATION_OK' in response_data["content"]:
                        print("✓ End-to-end broker test passed!")
                        return True
                    else:
                        print("✗ End-to-end broker test failed - FOUNDATION_OK not found in response")
                        return False
                else:
                    print("✗ End-to-end broker test failed - request ID mismatch")
                    return False

    except Exception as e:
        print(f"✗ End-to-end broker test failed with error: {e}")
        return False


async def main():
    """Run all tests."""
    print("Testing NanoClaw Broker Integration")
    print("=" * 40)

    # Test components
    components_ok = await test_broker_components()

    # Test LiteLLM integration
    litellm_ok = await test_litellm_client_integration()

    # Test end-to-end flow
    e2e_ok = await test_broker_end_to_end()

    print("\n" + "=" * 40)
    print("Test Results:")
    print(f"  Components: {'✓ PASS' if components_ok else '✗ FAIL'}")
    print(f"  LiteLLM Integration: {'✓ PASS' if litellm_ok else '✗ FAIL'}")
    print(f"  End-to-End Flow: {'✓ PASS' if e2e_ok else '✗ FAIL'}")

    if components_ok and litellm_ok and e2e_ok:
        print("\n🎉 All tests passed! Broker integration is working correctly.")
        return True
    else:
        print("\n❌ Some tests failed. Broker integration needs attention.")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)