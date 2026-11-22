"""Offline subprocess tests for the P01 Envoy collector."""

import subprocess
import sys
import unittest
from unittest.mock import patch

from testbed.experiments import collect_p01_envoy as collector


class TestP01Subprocess(unittest.TestCase):

    def run_child(self, code, timeout=5):
        real_popen = subprocess.Popen

        def fake_docker(command, **kwargs):
            self.assertEqual(
                command,
                ["docker", "logs", collector.CONTAINER],
            )

            return real_popen(
                [sys.executable, "-c", code],
                **kwargs
            )

        with patch.object(
            collector.subprocess,
            "Popen",
            side_effect=fake_docker,
        ):
            return collector.read_logs(timeout=timeout)

    def test_stalled_docker_command_times_out(self):
        code = "import time; time.sleep(2)"

        with self.assertRaises(TimeoutError):
            self.run_child(code, timeout=0.1)

    def test_successful_capture(self):
        result = self.run_child(
            "import sys; sys.stdout.buffer.write(b'hello\\n')"
        )
        self.assertEqual(result, b"hello\n")

    def test_nonzero_exit_rejected(self):
        with self.assertRaises(RuntimeError):
            self.run_child("import sys; sys.exit(7)")

    def test_oversized_capture_rejected(self):
        code = (
            "import sys; "
            "sys.stdout.buffer.write(b'x' * 9000000)"
        )

        with self.assertRaisesRegex(
            ValueError,
            "Docker logs exceed size limit",
        ):
            self.run_child(code)


if __name__ == "__main__":
    unittest.main()
