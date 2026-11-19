"""Offline subprocess tests; no Docker, network, or traffic generation."""

import subprocess
import sys
import unittest
from unittest.mock import patch

from experiments.docker_envoy_capture_final import (
    _bounded_read_process,
    CAPTURE_TIMEOUT_SECONDS,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def child(code):
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class TestDockerSubprocessFinal(unittest.TestCase):

    def test_successful_capture(self):
        proc = child("import sys; sys.stdout.buffer.write(b'capture\\n')")
        try:
            self.assertEqual(_bounded_read_process(proc), b"capture\n")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()

    def test_nonzero_exit_rejected(self):
        proc = child("import sys; sys.exit(7)")
        try:
            with self.assertRaises(TrafficEvidenceError):
                _bounded_read_process(proc)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()

    def test_stderr_rejected(self):
        proc = child(
            "import sys; sys.stderr.buffer.write(b'error\\n')"
        )
        try:
            with self.assertRaises(TrafficEvidenceError):
                _bounded_read_process(proc)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()

    def test_oversized_output_rejected(self):
        proc = child(
            "import sys; sys.stdout.buffer.write(b'x' * 1100000)"
        )
        try:
            with self.assertRaises(TrafficEvidenceError):
                _bounded_read_process(proc)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()

    def test_timeout_rejected(self):
        proc = child("import time; time.sleep(3)")
        try:
            with patch(
                "experiments.docker_envoy_capture_final.CAPTURE_TIMEOUT_SECONDS",
                0.1,
            ):
                with self.assertRaises(TrafficEvidenceError):
                    _bounded_read_process(proc)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
