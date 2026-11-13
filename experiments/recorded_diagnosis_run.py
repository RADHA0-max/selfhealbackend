"""Persist a bounded diagnosis capture using an injected RPC transport."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.dataset_runner import run_dataset
from experiments.live_diagnosis_runner import capture_diagnoses
from experiments.run_checkpoint import inspect_checkpoints, write_case_checkpoint
from experiments.run_record import RunRecordError, write_run_record
from experiments.run_reservation import reserve_run


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

    with reserve_run(directory, run_id):
        # Never replay a run with existing checkpoints.
        if inspect_checkpoints(directory, run_id):
            raise RunRecordError("run already has checkpoints")

        def checkpoint(case_id, *, status, response=None, error=None):
            write_case_checkpoint(
                directory,
                run_id,
                case_id,
                status=status,
                response=response,
                error=error,
            )

        # Canonical fingerprint identifies the in-memory dataset.
        dataset_sha256 = hashlib.sha256(
            json.dumps(
                dataset,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        result = capture_diagnoses(
            dataset,
            transport,
            model_id=model_id,
            run_id=run_id,
            checkpoint=checkpoint,
        )

        # The scorer requires every case ID. Missing responses remain
        # absent from the capture and count as invalid during evaluation.
        evaluation_responses = {
            case["case_id"]: result["partial_responses"].get(
                case["case_id"], ""
            )
            for case in dataset["cases"]
        }
        evaluation = run_dataset(dataset, evaluation_responses)

        return write_run_record(
            output_dir,
            run_id,
            {
                "schema_version": 1,
                "evaluation_mode": "recorded_capture_offline",
                "dataset_type": "synthetic",
                "dataset_fingerprint_method": "canonical_json_sha256",
                "dataset_sha256": dataset_sha256,
                "evaluation": evaluation,
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
