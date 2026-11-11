"""Offline tests for the bounded file-RPC diagnosis runner."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.file_rpc_diagnosis import diagnose_file_rpc
from agent.signal_adapter import SignalValidationError


class TestFileRPCDiagnosis(unittest.TestCase):
    def test_invalid_signal_rejected_before_rpc_construction(self):
        with patch(
            "agent.file_rpc_diagnosis.RPCClient"
        ) as client:
            with self.assertRaises(SignalValidationError):
                diagnose_file_rpc(
                    {"signal_id": "s1", "target": "api", "status": "503"},
                    "/unused/in",
                    "/unused/out",
                )
            client.assert_not_called()

    def test_valid_signal_uses_existing_client(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "in"
            outgoing = root / "out"
            incoming.mkdir()
            outgoing.mkdir()

            with patch(
                "agent.file_rpc_diagnosis.diagnose"
            ) as diagnosis:
                diagnose_file_rpc(
                    {"signal_id": "s1", "target": "api", "status": 503},
                    incoming,
                    outgoing,
                    timeout=1.0,
                )

                diagnosis.assert_called_once()
                rpc, evidence = diagnosis.call_args.args

                self.assertEqual(rpc.in_dir, incoming)
                self.assertEqual(rpc.out_dir, outgoing)
                self.assertEqual(rpc.timeout, 1.0)
                self.assertEqual(evidence["signal_id"], "s1")
                self.assertEqual(
                    evidence["probes"]["api"]["status"], 503
                )

    def test_missing_rpc_directories_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            with self.assertRaises(ValueError):
                diagnose_file_rpc(
                    {"signal_id": "s1", "target": "api", "status": 503},
                    root / "missing-in",
                    root / "missing-out",
                )


if __name__ == "__main__":
    unittest.main()
