"""Offline tests for launcher control flow; Docker is never invoked."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

from experiments import run_k6_final


class TestRunK6RuntimeFinal(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.results = Path(self.tmp.name)

        p = patch.object(run_k6_final, "RESULTS", self.results)
        p.start()
        self.addCleanup(p.stop)

    def invoke(self, run_id, execute, side_effect=None):
        args = ["run_k6_final", "--run-id", run_id]
        if execute:
            args.append("--execute")

        with patch.object(sys, "argv", args):
            with patch.object(
                run_k6_final.subprocess,
                "run",
                side_effect=side_effect,
            ) as mocked:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    with contextlib.redirect_stderr(io.StringIO()):
                        try:
                            run_k6_final.main()
                            exit_code = 0
                        except SystemExit as exc:
                            exit_code = exc.code

        return exit_code, out.getvalue(), mocked

    def receipt(self, run_id):
        return json.loads(
            (self.results / f"{run_id}.reserved/status.json").read_text()
        )

    def test_dry_run_never_calls_docker(self):
        code, output, mocked = self.invoke("dryA", False)
        self.assertEqual(code, 0)
        self.assertIn("READY_NOT_EXECUTED", output)
        mocked.assert_not_called()
        self.assertFalse((self.results / "dryA.reserved").exists())

    def test_missing_dependencies_fail_closed(self):
        check = subprocess.CompletedProcess([], 0, "testbed-app\n", "")
        code, _, mocked = self.invoke("missingA", True, [check])
        self.assertEqual(code, 125)
        self.assertEqual(self.receipt("missingA")["status"], "PREFLIGHT_FAILED")
        self.assertEqual(mocked.call_count, 1)

    def test_preflight_nonzero_fails_closed(self):
        check = subprocess.CompletedProcess([], 1, "", "docker unavailable")
        code, _, mocked = self.invoke("preflightA", True, [check])
        self.assertEqual(code, 125)
        self.assertEqual(self.receipt("preflightA")["status"], "PREFLIGHT_FAILED")
        self.assertEqual(mocked.call_count, 1)

    def test_timeout_attempts_cleanup(self):
        ready = subprocess.CompletedProcess(
            [], 0, "testbed-envoy\ntestbed-app\n", ""
        )
        timeout = subprocess.TimeoutExpired("docker", 90)
        cleanup = subprocess.CompletedProcess([], 0, "", "")

        code, _, mocked = self.invoke(
            "timeoutA", True, [ready, timeout, cleanup]
        )

        self.assertEqual(code, 124)
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(self.receipt("timeoutA")["status"], "TIMED_OUT")

    def test_cleanup_failure_is_recorded(self):
        ready = subprocess.CompletedProcess(
            [], 0, "testbed-envoy\ntestbed-app\n", ""
        )
        timeout = subprocess.TimeoutExpired("docker", 90)
        cleanup = subprocess.CompletedProcess([], 1, "", "")

        code, _, mocked = self.invoke(
            "cleanupA", True, [ready, timeout, cleanup]
        )

        self.assertEqual(code, 124)
        self.assertEqual(
            self.receipt("cleanupA")["status"],
            "TIMED_OUT_CLEANUP_FAILED",
        )


if __name__ == "__main__":
    unittest.main()
