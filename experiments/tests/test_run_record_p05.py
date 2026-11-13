import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments.run_record import (
    RunRecordError,
    write_run_record,
)


class RunRecordTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_atomic_write(self):
        path = write_run_record(
            self.directory,
            "p05-001",
            {"completed": 1, "failures": {}},
        )

        self.assertEqual(path.name, "run-p05-001.json")
        self.assertEqual(
            json.loads(path.read_text()),
            {"completed": 1, "failures": {}},
        )
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            list(self.directory.glob(".tmp-*")),
            [],
        )

    def test_existing_record_not_overwritten(self):
        path = write_run_record(
            self.directory, "same", {"value": 1}
        )

        with self.assertRaises(RunRecordError):
            write_run_record(
                self.directory, "same", {"value": 2}
            )

        self.assertEqual(
            json.loads(path.read_text()),
            {"value": 1},
        )

    def test_invalid_run_id(self):
        for run_id in ("../escape", "bad/name", "", "a" * 65):
            with self.subTest(run_id=run_id):
                with self.assertRaises(RunRecordError):
                    write_run_record(
                        self.directory, run_id, {"value": 1}
                    )

        self.assertEqual(list(self.directory.iterdir()), [])

    def test_oversized_record(self):
        with self.assertRaises(RunRecordError):
            write_run_record(
                self.directory,
                "large",
                {"content": "x" * (1024 * 1024)},
            )

        self.assertEqual(list(self.directory.iterdir()), [])

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(RunRecordError):
            write_run_record(
                self.directory,
                "nan",
                {"confidence": float("nan")},
            )

    def test_missing_directory(self):
        with self.assertRaises(RunRecordError):
            write_run_record(
                self.directory / "missing",
                "test",
                {"value": 1},
            )

    def test_existing_symlink_not_overwritten(self):
        target = self.directory / "target.json"
        target.write_text('{"original":true}')

        link = self.directory / "run-linked.json"
        link.symlink_to(target)

        with self.assertRaises(RunRecordError):
            write_run_record(
                self.directory,
                "linked",
                {"original": False},
            )

        self.assertEqual(
            target.read_text(),
            '{"original":true}',
        )


if __name__ == "__main__":
    unittest.main()
