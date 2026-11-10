import json
import unittest
import uuid

from broker.protocol import parse_request, make_response, MAX_REQUEST_BYTES


class TestRPCContract(unittest.TestCase):

    def valid_request(self):
        return {
            "request_id": uuid.uuid4().hex,
            "model": "fast",
            "messages": [
                {
                    "role": "user",
                    "content": "Diagnose synthetic HTTP 503 errors."
                }
            ],
            "max_tokens": 256,
            "temperature": 0.0,
        }

    def test_valid_request(self):
        payload = json.dumps(self.valid_request()).encode()
        request = parse_request(payload)

        self.assertEqual(request.model, "fast")
        self.assertEqual(request.max_tokens, 256)

    def test_reject_unknown_model(self):
        data = self.valid_request()
        data["model"] = "qwen2.5:7b-q8_0"

        with self.assertRaises(ValueError):
            parse_request(json.dumps(data).encode())

    def test_reject_unknown_field(self):
        data = self.valid_request()
        data["network_access"] = True

        with self.assertRaises(ValueError):
            parse_request(json.dumps(data).encode())

    def test_reject_oversized_request(self):
        data = self.valid_request()
        data["messages"][0]["content"] = "X" * MAX_REQUEST_BYTES

        with self.assertRaises(ValueError):
            parse_request(json.dumps(data).encode())

    def test_reject_duplicate_json_keys(self):
        payload = (
            b'{"request_id":"abc","model":"fast",'
            b'"model":"deep","messages":[{"role":"user","content":"test"}]}'
        )

        with self.assertRaises(ValueError):
            parse_request(payload)

    def test_response_schema(self):
        request_id = uuid.uuid4().hex
        response = json.loads(
            make_response(request_id, content='{"status":"ok"}')
        )

        self.assertEqual(response["request_id"], request_id)
        self.assertTrue(response["ok"])
        self.assertEqual(response["content"], '{"status":"ok"}')
        self.assertIsNone(response["error"])


if __name__ == "__main__":
    unittest.main()
