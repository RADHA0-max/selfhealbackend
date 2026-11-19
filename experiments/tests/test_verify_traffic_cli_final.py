"""CLI exit-code verification using offline evidence fixtures."""

import contextlib
import io
import json
import sys
import unittest
from unittest.mock import patch

from experiments.verify_traffic_final import main


class VerifyTrafficCLITests(unittest.TestCase):
    def setUp(self):
        from experiments.tests.test_verify_traffic_final import VerifyTrafficTests
        self.fixture = VerifyTrafficTests(
            methodName="test_1200_request_end_to_end"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def invoke(self, allow_partial=False):
        args = [
            "verify_traffic_final",
            "--k6", str(self.fixture.k6),
            "--envoy", str(self.fixture.envoy),
            "--run-id", self.fixture.run_id,
        ]

        if allow_partial:
            args.append("--allow-partial")

        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.object(sys, "argv", args):
            with contextlib.redirect_stdout(stdout):
                with contextlib.redirect_stderr(stderr):
                    code = main()

        return code, stdout.getvalue(), stderr.getvalue()

    def test_complete_run_exit_zero(self):
        self.fixture.write_fixture(count=1200)

        code, stdout, stderr = self.invoke()

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")

        result = json.loads(stdout)["result"]

        self.assertEqual(result["workload_status"], "COMPLETE")
        self.assertTrue(result["request_ids_match"])

    def test_partial_run_default_exit_one(self):
        self.fixture.write_fixture(count=20)

        code, stdout, stderr = self.invoke()

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertFalse(json.loads(stderr)["ok"])

    def test_partial_run_explicitly_allowed(self):
        self.fixture.write_fixture(count=20)

        code, stdout, stderr = self.invoke(allow_partial=True)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")

        result = json.loads(stdout)["result"]

        self.assertEqual(result["workload_status"], "PARTIAL")
        self.assertFalse(result["scheduled_iterations_complete"])

    def test_mismatched_envoy_evidence_exit_one(self):
        self.fixture.write_fixture(count=20, missing=7)

        code, stdout, stderr = self.invoke(allow_partial=True)

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertFalse(json.loads(stderr)["ok"])


if __name__ == "__main__":
    unittest.main()
