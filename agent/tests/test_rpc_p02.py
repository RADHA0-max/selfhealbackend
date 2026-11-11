"""P02 offline regression tests for file-RPC response validation."""

import json
import unittest

from agent.rpc_client import RPCError
from agent.tests import test_rpc_security as security


class TestRPCP02(unittest.TestCase):
    setUp = security.TestRPCSecurity.setUp
    simulate_response = security.TestRPCSecurity.simulate_response


    def test_reject_failed_response_with_content(self):
        def factory(request_id):
            return json.dumps({
                "request_id": request_id,
                "ok": False,
                "content": "unexpected success",
                "embedding": None,
                "error": "broker failed",
            }).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(factory)

    def test_reject_failed_response_with_embedding(self):
        def factory(request_id):
            return json.dumps({
                "request_id": request_id,
                "ok": False,
                "content": None,
                "embedding": [0.1],
                "error": "broker failed",
            }).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(factory)

    def test_reject_nonfinite_json_constant(self):
        def factory(request_id):
            return (
                '{"request_id":"%s","ok":true,'
                '"content":null,"embedding":null,"error":NaN}'
                % request_id
            ).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(factory)

    def test_reject_nonstring_request_id(self):
        def factory(request_id):
            return json.dumps({
                "request_id": 123,
                "ok": True,
                "content": "test",
                "embedding": None,
                "error": None,
            }).encode()

        with self.assertRaises(RPCError):
            self.simulate_response(factory)


if __name__ == "__main__":
    unittest.main()
