"""Regression tests for bounded P06 reliability record capacity."""

import json
import tempfile
import unittest
from pathlib import Path

from experiments.run_record import (
    RunRecordError,
    write_run_record,
)


class ReliabilityCapacityTests(unittest.TestCase):

    def test_large_final_record_can_be_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            record = {"responses": ["x" * 16384] * 100}

            path = write_run_record(
                directory,
                "capacity-001",
                record,
                max_bytes=4 * 1024 * 1024,
            )

            self.assertEqual(
                json.loads(Path(path).read_text()),
                record,
            )

    def test_default_record_limit_remains_one_mib(self):
        with tempfile.TemporaryDirectory() as directory:
            record = {"payload": "x" * (1024 * 1024)}

            with self.assertRaises(RunRecordError):
                write_run_record(directory, "capacity-002", record)

    def test_rejects_excessive_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RunRecordError):
                write_run_record(
                    directory,
                    "capacity-003",
                    {"ok": True},
                    max_bytes=8 * 1024 * 1024,
                )


if __name__ == "__main__":
    unittest.main()
