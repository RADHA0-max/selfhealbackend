"""Atomic, bounded checkpoints for diagnosis evaluation cases."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from experiments.response_capture import MAX_RESPONSE_BYTES
from experiments.run_record import RUN_ID, RunRecordError, write_run_record


CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


class CheckpointError(RunRecordError):
    """Invalid or conflicting checkpoint."""


def write_case_checkpoint(
    directory: str | Path,
    run_id: str,
    case_id: str,
    *,
    status: str,
    response: str | None = None,
    error: str | None = None,
) -> Path:
    """Create an immutable checkpoint for one case."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise CheckpointError("invalid run ID")

    if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
        raise CheckpointError("invalid case ID")

    if status not in ("completed", "failed", "uncertain"):
        raise CheckpointError("invalid checkpoint status")

    if status == "completed":
        if not isinstance(response, str) or error is not None:
            raise CheckpointError("completed checkpoint requires response")
    elif response is not None:
        raise CheckpointError("non-completed checkpoint cannot contain response")

    if error is not None and (
        not isinstance(error, str) or len(error) > 128
    ):
        raise CheckpointError("invalid error label")

    if response is not None and (
        len(response.encode("utf-8")) > MAX_RESPONSE_BYTES
    ):
        raise CheckpointError("response exceeds capture limit")

    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise CheckpointError("invalid checkpoint directory")

    record: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "case_id": case_id,
        "status": status,
        "response": response,
        "error": error,
    }

    # Each run has a distinct namespace; no ambiguous concatenation.
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    checkpoint_dir = Path(directory) / ("checkpoints-" + digest)

    checkpoint_dir.mkdir(mode=0o700, exist_ok=True)

    return write_run_record(
        checkpoint_dir,
        case_id,
        record,
    )


def inspect_checkpoints(
    directory: str | Path,
    run_id: str,
) -> dict[str, Any]:
    """Read checkpoints for inspection only; never resume inference."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise CheckpointError("invalid run ID")

    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    checkpoint_dir = Path(directory) / ("checkpoints-" + digest)

    if not checkpoint_dir.is_dir():
        return {}

    checkpoints = {}

    for path in sorted(checkpoint_dir.glob("run-*.json")):
        try:
            if path.is_symlink() or path.stat().st_size > 1024 * 1024:
                raise CheckpointError("unsafe checkpoint file")

            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise CheckpointError("invalid checkpoint JSON") from exc

        if not isinstance(data, dict):
            raise CheckpointError("checkpoint must be an object")

        if set(data) != {
            "schema_version", "run_id", "case_id",
            "status", "response", "error",
        } or data["schema_version"] != 1:
            raise CheckpointError("invalid checkpoint schema")

        case_id = data["case_id"]

        if (
            not isinstance(case_id, str)
            or not CASE_ID.fullmatch(case_id)
            or data["run_id"] != run_id
            or path.name != "run-" + case_id + ".json"
        ):
            raise CheckpointError("checkpoint identity mismatch")

        status = data["status"]
        response = data["response"]
        error = data["error"]

        if status not in ("completed", "failed", "uncertain"):
            raise CheckpointError("invalid checkpoint status")

        if status == "completed":
            if not isinstance(response, str) or error is not None:
                raise CheckpointError("invalid completed checkpoint")
            if len(response.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise CheckpointError("oversized checkpoint response")
        elif response is not None:
            raise CheckpointError("invalid incomplete checkpoint")

        if error is not None and (
            not isinstance(error, str) or len(error) > 128
        ):
            raise CheckpointError("invalid checkpoint error")

        if case_id in checkpoints:
            raise CheckpointError("duplicate checkpoint case ID")

        checkpoints[case_id] = data

    return checkpoints
