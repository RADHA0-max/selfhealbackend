"""Bounded atomic storage for offline diagnosis evaluation records."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any


MAX_RECORD_BYTES = 1024 * 1024
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


class RunRecordError(ValueError):
    """Invalid or unsafe evaluation record."""


def write_run_record(
    directory: str | Path,
    run_id: str,
    record: dict[str, Any],
) -> Path:
    """Create one bounded record without overwriting an existing run."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise RunRecordError("invalid run ID")

    if not isinstance(record, dict):
        raise RunRecordError("record must be an object")

    directory = Path(directory)

    if not directory.is_dir():
        raise RunRecordError("output directory does not exist")

    try:
        payload = json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RunRecordError("record is not valid JSON") from exc

    if len(payload) > MAX_RECORD_BYTES:
        raise RunRecordError("record exceeds 1 MiB")

    destination = directory / ("run-" + run_id + ".json")
    temporary = directory / (
        ".tmp-" + run_id + "-" + uuid.uuid4().hex
    )

    if destination.exists():
        raise RunRecordError("run record already exists")

    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )

        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        os.link(temporary, destination)

        directory_fd = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY,
        )

        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    except FileExistsError as exc:
        raise RunRecordError("run record already exists") from exc

    finally:
        temporary.unlink(missing_ok=True)

    return destination
