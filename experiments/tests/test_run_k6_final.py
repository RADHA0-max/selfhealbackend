import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import run_k6_final


class TestRunK6Final(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.results = Path(self.temp.name)
        self.patch = patch.object(run_k6_final, "RESULTS", self.results)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_valid_run_id(self):
        capture = run_k6_final.prepare("run_20261118_A")
        self.assertEqual(capture.name, "run_20261118_A.jsonl")

    def test_rejects_path_traversal(self):
        for value in ("../escape", "a/b", "", ".hidden", "a" * 33):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    run_k6_final.prepare(value)

    def test_rejects_existing_capture(self):
        (self.results / "existing.jsonl").write_text("old")
        with self.assertRaises(FileExistsError):
            run_k6_final.prepare("existing")

    def test_rejects_symlink_capture(self):
        (self.results / "linked.jsonl").symlink_to(
            self.results / "missing.jsonl"
        )
        with self.assertRaises(FileExistsError):
            run_k6_final.prepare("linked")

    def test_missing_results_directory(self):
        with patch.object(
            run_k6_final,
            "RESULTS",
            self.results / "missing",
        ):
            with self.assertRaises(ValueError):
                run_k6_final.prepare("valid")


if __name__ == "__main__":
    unittest.main()
