import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from selfhealbench.bench.diagnose import main
from selfhealbench.bench.pilot import NanoClawAgent, prepare_evidence
from selfhealbench.bench.run import replay, load_scenarios


class PreflightTests(unittest.TestCase):
    def test_existing_diagnostic_report_prevents_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.json").write_text("{}")
            (root / "result.json").write_text("preserved")
            argv = ["diagnose", "--nanoclaw-root", str(root), "--rpc-in", str(root),
                    "--rpc-out", str(root), "--model", "fast",
                    "--evidence", str(root / "evidence.json"), "--out", str(root / "result.json"),
                    "--approved-inference-only"]
            with patch("sys.argv", argv), patch(
                    "selfhealbench.bench.diagnose.NanoClawDiagnosticTransport") as transport:
                with self.assertRaises(FileExistsError):
                    main()
                transport.return_value.request.assert_not_called()
            self.assertEqual((root / "result.json").read_text(), "preserved")

    def test_nested_credentials_and_labels_removed(self):
        evidence = prepare_evidence({"probes": {"db": {
            "token": "private", "ground_truth": "db", "status": 503}},
            "docker_logs": "Authorization: Bearer abc123 token=othersecret"})
        text = json.dumps(evidence)
        for value in ("private", "ground_truth", "abc123", "othersecret"):
            self.assertNotIn(value, text)

    def test_timeout_survives_adapter_and_is_counted(self):
        class Transport:
            def request(self, prompt): raise TimeoutError("fixture timeout")
        report = replay(load_scenarios(), {"SHB-001": {"before": {}}},
                        NanoClawAgent(Transport()))
        self.assertEqual(report["timeouts"], 1)
        self.assertEqual(report["completed"], 0)
