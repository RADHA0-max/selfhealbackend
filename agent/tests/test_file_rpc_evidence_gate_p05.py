"""Verify file-RPC diagnosis applies the evidence gate."""

import unittest
from unittest.mock import patch

from agent.file_rpc_diagnosis import diagnose_file_rpc


class FileRPCEvidenceGateTests(unittest.TestCase):
    def test_unsupported_dependency_is_downgraded(self):
        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.calls = 0

            def call(self, model, messages, **kwargs):
                self.calls += 1
                return {
                    "ok": True,
                    "content": (
                        '{"category":"dependency_failure",'
                        '"target":"api",'
                        '"confidence":0.9,'
                        '"summary":"Suspected dependency failure",'
                        '"recommended_action":"investigate_api"}'
                    ),
                }

        client = FakeClient()

        with patch(
            "agent.file_rpc_diagnosis.RPCClient",
            return_value=client,
        ):
            result = diagnose_file_rpc(
                {"signal_id": "gate-rpc-001", "target": "api", "status": 503},
                "/unused/in",
                "/unused/out",
            )

        self.assertEqual(client.calls, 1)
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.target, "api")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.recommended_action, "collect_more_evidence")


if __name__ == "__main__":
    unittest.main()
