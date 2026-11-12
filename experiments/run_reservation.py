"""Exclusive run reservations for diagnosis evaluations."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from experiments.run_record import RUN_ID, RunRecordError


@contextmanager
def reserve_run(
    directory: str | Path,
    run_id: str,
) -> Iterator[None]:
    """Reserve a run exclusively; never overwrite existing records."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise RunRecordError("invalid run ID")

    directory = Path(directory)

    if not directory.is_dir():
        raise RunRecordError("output directory does not exist")

    destination = directory / ("run-" + run_id + ".json")
    reservation = directory / (".reserve-" + run_id)

    if destination.exists() or destination.is_symlink():
        raise RunRecordError("run record already exists")

    try:
        fd = os.open(
            reservation,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise RunRecordError("run already reserved") from exc

    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
            stream.flush()
            os.fsync(stream.fileno())

        # Recheck after reservation to close the initial existence race.
        if destination.exists() or destination.is_symlink():
            raise RunRecordError("run record already exists")

        yield

    finally:
        reservation.unlink(missing_ok=True)
