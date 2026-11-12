"""Evaluate externally captured responses without claiming verified inference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.dataset_loader import load_dataset
from experiments.dataset_runner import run_dataset
from experiments.response_capture import load_capture


def evaluate_capture(
    dataset_path: Path,
    capture_path: Path,
) -> dict[str, Any]:
    """Score a captured response set using existing offline evaluation logic."""
    dataset_path = Path(dataset_path)
    capture_path = Path(capture_path)

    # Validate dataset before evaluating captured responses.
    load_dataset(dataset_path)
    dataset_bytes = dataset_path.read_bytes()
    dataset = json.loads(dataset_bytes)

    responses = load_capture(capture_path, dataset)
    evaluation = run_dataset(dataset, responses)

    return {
        "evaluation_mode": "external_capture_offline",
        "inference_verified": False,
        "dataset_type": "synthetic",
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "capture_sha256": hashlib.sha256(
            capture_path.read_bytes()
        ).hexdigest(),
        "requested": evaluation["requested"],
        "completed": evaluation["completed"],
        "valid_decision_rate": evaluation["valid_decision_rate"],
        "exact_match_rate": evaluation["exact_match_rate"],
        "correct_given_valid_rate": evaluation["correct_given_valid_rate"],
        "status_counts": evaluation["status_counts"],
        "recovery_success": None,
        "results": evaluation["results"],
    }
