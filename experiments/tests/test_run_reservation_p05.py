import tempfile
import unittest
from pathlib import Path

from experiments.run_reservation import reserve_run
from experiments.run_record import RunRecordError


class ReservationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_reservation_blocks_duplicate(self):
        with reserve_run(self.directory, "same"):
            with self.assertRaises(RunRecordError):
                with reserve_run(self.directory, "same"):
                    pass

    def test_reservation_released(self):
        with reserve_run(self.directory, "released"):
            pass

        self.assertFalse(
            (self.directory / ".reserve-released").exists()
        )

    def test_existing_record_rejected(self):
        (self.directory / "run-existing.json").write_text("{}")

        with self.assertRaises(RunRecordError):
            with reserve_run(self.directory, "existing"):
                pass

    def test_invalid_id_rejected(self):
        with self.assertRaises(RunRecordError):
            with reserve_run(self.directory, "../escape"):
                pass

    def test_reservation_survives_nested_failure(self):
        with self.assertRaises(RuntimeError):
            with reserve_run(self.directory, "failed"):
                raise RuntimeError("simulated failure")

        self.assertFalse(
            (self.directory / ".reserve-failed").exists()
        )


if __name__ == "__main__":
    unittest.main()
