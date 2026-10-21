import json
import unittest

from integration.nanoclaw_adapter import (
    NanoClawBenchAdapter,
    NanoClawAdapterError,
)


VALID = {
    "root_cause": "Database unavailable",
    "action": "restart",
    "target": "database",
    "reason": "Connection probe failed",
}


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.prompts = []

    def request(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.response


class AdapterTests(unittest.TestCase):

    def test_prompt_requires_nanoclaw_delivery_wrapper(self):
        from integration.nanoclaw_adapter import NanoClawBenchAdapter

        class RecordingTransport:
            def __init__(self):
                self.prompt = None

            def request(self, prompt):
                self.prompt = prompt
                return (
                    '{"root_cause":"database unavailable",'
                    '"action":"none","target":"database",'
                    '"reason":"connection refused"}'
                )

        transport = RecordingTransport()
        NanoClawBenchAdapter(transport).diagnose({"probes": {}})

        self.assertIn('<message to="local-cli">', transport.prompt)
        self.assertIn("</message>", transport.prompt)
        self.assertIn("INSIDE the message wrapper", transport.prompt)
        self.assertIn("Do not execute remediation", transport.prompt)

    def test_valid_diagnosis(self):
        transport = FakeTransport(json.dumps(VALID))
        result = NanoClawBenchAdapter(transport).diagnose({
            "probes": {"database": "failed"},
            "docker_logs": "connection refused",
            "prometheus": {"up": 0},
        })
        self.assertEqual(result, VALID)
        self.assertIn("connection refused", transport.prompts[0])

    def test_healthy_no_action(self):
        healthy = {
            "root_cause": "none",
            "action": "none",
            "target": "none",
            "reason": "All checks healthy",
        }
        result = NanoClawBenchAdapter(
            FakeTransport(json.dumps(healthy))
        ).diagnose({"probes": {"healthy": True}})
        self.assertEqual(result["action"], "none")

    def test_missing_telemetry(self):
        transport = FakeTransport(json.dumps(VALID))
        NanoClawBenchAdapter(transport).diagnose({})
        prompt = transport.prompts[0]
        self.assertIn('"probes": {}', prompt)
        self.assertIn('"prometheus": {}', prompt)

    def test_logs_truncated(self):
        transport = FakeTransport(json.dumps(VALID))
        NanoClawBenchAdapter(transport).diagnose({
            "docker_logs": "A" * 9000 + "END",
        })
        prompt = transport.prompts[0]
        self.assertIn("END", prompt)
        self.assertNotIn("A" * 9000, prompt)

    def test_invalid_model_response(self):
        with self.assertRaisesRegex(
            NanoClawAdapterError, "invalid diagnosis JSON"
        ):
            NanoClawBenchAdapter(
                FakeTransport("not-json")
            ).diagnose({})

    def test_transport_failure(self):
        with self.assertRaisesRegex(
            NanoClawAdapterError, "request failed"
        ):
            NanoClawBenchAdapter(
                FakeTransport(error=TimeoutError("broker timeout"))
            ).diagnose({})

    def test_duplicate_fields_rejected(self):
        response = '{"root_cause":"db","action":"no_op","action":"clear_fault","target":"db","reason":"failure"}'
        with self.assertRaises(NanoClawAdapterError):
            NanoClawBenchAdapter(FakeTransport(response)).diagnose({})

    def test_oversized_response_rejected(self):
        with self.assertRaises(NanoClawAdapterError):
            NanoClawBenchAdapter(FakeTransport("x" * 65000)).diagnose({})


if __name__ == "__main__":
    unittest.main()
