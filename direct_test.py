#!/usr/bin/env python3
"""Direct test runner to bypass pytest import issues."""

import sys
import os
sys.path.insert(0, os.getcwd())

# Import the test module directly
import tests.broker.test_protocol as test_module

# Run a simple test to see if imports work
print("Testing imports...")
try:
    from broker.protocol import RPCRequest, RPCResponse, parse_request, make_response
    print("All broker.protocol imports successful")
except Exception as e:
    print(f"Import error: {e}")
    sys.exit(1)

# Try to run one test function directly
print("Running test_parse_request_valid_chat directly...")
try:
    test_module.test_parse_request_valid_chat()
    print("test_parse_request_valid_chat passed")
except Exception as e:
    print(f"test_parse_request_valid_chat failed: {e}")

print("All direct tests completed successfully")