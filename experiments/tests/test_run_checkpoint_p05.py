import json
import tempfile
import unittest
from pathlib import Path

from experiments.run_checkpoint import (
    CheckpointError,
    inspect_checkpoints,
    write_case_checkpoint,
)


class CheckpointTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_completed_checkpoint_roundtrip(self):
        path = write_case_checkpoint(
            self.directory, "run1", "case1",
            status="completed", response='{"ok":true}',
        )

        records = inspect_checkpoints(self.directory, "run1")

        self.assertEqual(records["case1"]["status"], "completed")
        self.assertEqual(
            records["case1"]["response"], '{"ok":true}'
        )
        self.assertTrue(path.exists())

    def test_duplicate_checkpoint_rejected(self):
        write_case_checkpoint(
            self.directory, "run1", "case1",
            status="completed", response="first",
        )

        with self.assertRaises(ValueError):
            write_case_checkpoint(
                self.directory, "run1", "case1",
                status="completed", response="second",
            )

        self.assertEqual(
            inspect_checkpoints(self.directory, "run1")["case1"]["response"],
            "first",
        )

    def test_run_namespace_collision_prevented(self):
        write_case_checkpoint(
            self.directory, "alpha-case-beta", "gamma",
            status="completed", response="first",
        )

        write_case_checkpoint(
            self.directory, "alpha", "beta-case-gamma",
            status="completed", response="second",
        )

        self.assertEqual(
            len(inspect_checkpoints(self.directory, "alpha-case-beta")),
            1,
        )
        self.assertEqual(
            len(inspect_checkpoints(self.directory, "alpha")),
            1,
        )

    def test_invalid_checkpoint_state(self):
        with self.assertRaises(CheckpointError):
            write_case_checkpoint(
                self.directory, "run1", "case1",
                status="completed",
            )

        with self.assertRaises(CheckpointError):
            write_case_checkpoint(
                self.directory, "run1", "case1",
                status="failed", response="unexpected",
            )

    def test_invalid_identifiers(self):
        for run_id, case_id in (
            ("../escape", "case1"),
            ("run1", "../escape"),
            ("", "case1"),
        ):
            with self.subTest(run_id=run_id, case_id=case_id):
                with self.assertRaises(CheckpointError):
                    write_case_checkpoint(
                        self.directory, run_id, case_id,
                        status="uncertain",
                    )

    def test_tampered_run_identity_rejected(self):
        path = write_case_checkpoint(
            self.directory, "run1", "case1",
            status="completed", response="valid",
        )

        data = json.loads(path.read_text())
        data["run_id"] = "different"
        path.write_text(json.dumps(data))

        with self.assertRaises(CheckpointError):
            inspect_checkpoints(self.directory, "run1")

    def test_tampered_case_identity_rejected(self):
        path = write_case_checkpoint(
            self.directory, "run1", "case1",
            status="completed", response="valid",
        )

        data = json.loads(path.read_text())
        data["case_id"] = "case2"
        path.write_text(json.dumps(data))

        with self.assertRaises(CheckpointError):
            inspect_checkpoints(self.directory, "run1")

    def test_oversized_checkpoint_rejected(self):
        with self.assertRaises(ValueError):
            write_case_checkpoint(
                self.directory, "run1", "case1",
                status="completed",
                response="x" * (1024 * 1024),
            )

    def test_missing_run_returns_empty(self):
        self.assertEqual(
            inspect_checkpoints(self.directory, "missing"),
            {},
        )

    def test_failed_checkpoint_roundtrip(self):
        write_case_checkpoint(
            self.directory, "run1", "case1",
            status="failed", error="TimeoutError",
        )

        record = inspect_checkpoints(
            self.directory, "run1"
        )["case1"]

        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error"], "TimeoutError")
        self.assertIsNone(record["response"])


    def test_response_capture_limit(self):
        from experiments.response_capture import MAX_RESPONSE_BYTES

        with self.assertRaises(CheckpointError):
            write_case_checkpoint(
                self.directory, "run1", "case1",
                status="completed",
                response="x" * (MAX_RESPONSE_BYTES + 1),
            )

    def test_missing_output_directory_rejected(self):
        missing = self.directory / "missing"

        with self.assertRaises(CheckpointError):
            write_case_checkpoint(
                missing, "run1", "case1",
                status="uncertain",
            )

        self.assertFalse(missing.exists())

    def test_tampered_oversized_response_rejected(self):
        from experiments.response_capture import MAX_RESPONSE_BYTES

        path = write_case_checkpoint(
            self.directory, "run1", "case1",
            status="completed", response="valid",
        )

        data = json.loads(path.read_text())
        data["response"] = "x" * (MAX_RESPONSE_BYTES + 1)
        path.write_text(json.dumps(data))

        with self.assertRaises(CheckpointError):
            inspect_checkpoints(self.directory, "run1")

    def test_symlink_output_directory_rejected(self):
        link = self.directory / "linked"
        link.symlink_to(self.directory, target_is_directory=True)

        with self.assertRaises(CheckpointError):
            write_case_checkpoint(
                link, "run1", "case1",
                status="uncertain",
            )


if __name__ == "__main__":
    unittest.main()
