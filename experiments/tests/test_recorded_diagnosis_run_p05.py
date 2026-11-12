import json
import tempfile
import unittest
from pathlib import Path

from experiments.recorded_diagnosis_run import run_and_record
from experiments.tests.test_live_diagnosis_runner_p05 import (
    FakeTransport,
    dataset,
)


class RecordedRunTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_complete_run_is_saved(self):
        path = run_and_record(
            dataset(),
            FakeTransport(),
            model_id="fast",
            run_id="complete",
            output_dir=self.directory,
        )

        record = json.loads(path.read_text())

        self.assertEqual(record["requested"], 1)
        self.assertEqual(record["completed"], 1)
        self.assertEqual(record["failures"], {})
        self.assertIsNotNone(record["capture"])
        self.assertFalse(record["inference_verified"])
        self.assertIsNone(record["recovery_success"])

    def test_failed_run_is_saved(self):
        path = run_and_record(
            dataset(),
            FakeTransport(error=TimeoutError("timeout")),
            model_id="fast",
            run_id="failed",
            output_dir=self.directory,
        )

        record = json.loads(path.read_text())

        self.assertEqual(record["requested"], 1)
        self.assertEqual(record["completed"], 0)
        self.assertIsNone(record["capture"])
        self.assertEqual(
            record["failures"]["p05-test-001"],
            "TimeoutError",
        )

    def test_duplicate_run_does_not_overwrite(self):
        run_and_record(
            dataset(),
            FakeTransport(),
            model_id="fast",
            run_id="duplicate",
            output_dir=self.directory,
        )

        duplicate_transport = FakeTransport()

        with self.assertRaises(ValueError):
            run_and_record(
                dataset(),
                duplicate_transport,
                model_id="fast",
                run_id="duplicate",
                output_dir=self.directory,
            )

        self.assertEqual(duplicate_transport.calls, 0)

        self.assertEqual(
            len(list(self.directory.glob("run-*.json"))),
            1,
        )


if __name__ == "__main__":
    unittest.main()
