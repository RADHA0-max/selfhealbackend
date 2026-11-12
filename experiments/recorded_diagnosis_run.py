"""Persist a bounded diagnosis capture using an injected RPC transport."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.live_diagnosis_runner import capture_diagnoses
from experiments.run_record import RunRecordError, write_run_record


def run_and_record(
    dataset: dict[str, Any],
    transport: Any,
    *,
    model_id: str,
    run_id: str,
    output_dir: str | Path,
) -> Path:
    """Run diagnosis capture and atomically store its outcome."""
    if not isinstance(run_id, str):
        raise RunRecordError("invalid run ID")

    # Reject existing records before issuing any inference requests.
    from experiments.run_record import RUN_ID

    if not RUN_ID.fullmatch(run_id):
        raise RunRecordError("invalid run ID")

    directory = Path(output_dir)
    if not directory.is_dir():
        raise RunRecordError("output directory does not exist")

    if (directory / ("run-" + run_id + ".json")).exists():
        raise RunRecordError("run record already exists")

    result = capture_diagnoses(
        dataset,
        transport,
        model_id=model_id,
        run_id=run_id,
    )

    return write_run_record(
        output_dir,
        run_id,
        {
            "schema_version": 1,
            "run_id": run_id,
            "model_id": model_id,
            "requested": result["requested"],
            "completed": result["completed"],
            "failures": result["failures"],
            "capture": result["capture"],
            "partial_responses": result["partial_responses"],
            "inference_verified": False,
            "recovery_success": None,
        },
    )
