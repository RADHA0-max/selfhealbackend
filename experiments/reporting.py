"""Deterministic metadata for synthetic offline evaluations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def build_report(
    dataset_path: Path,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    """Attach dataset integrity metadata without claiming live inference."""
    raw = dataset_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    data = json.loads(raw)
    rows = evaluation["results"]

    expected_ids = [case["case_id"] for case in data["cases"]]
    actual_ids = [row["case_id"] for row in rows]

    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("duplicate dataset case IDs")

    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("duplicate evaluation case IDs")

    if set(actual_ids) != set(expected_ids):
        raise ValueError("evaluation does not match dataset")

    if evaluation.get("mode") != "synthetic_offline":
        raise ValueError("unsupported evaluation mode")

    if evaluation.get("dataset_type") != "synthetic":
        raise ValueError("unsupported dataset type")

    if len(rows) != evaluation["requested"]:
        raise ValueError("result count mismatch")

    if evaluation.get("recovery_success") is not None:
        raise ValueError("offline evaluation cannot claim recovery")

    failures = Counter(
        row["failure_reason"]
        for row in rows
        if row["failure_reason"] is not None
    )

    return {
        "report_version": 1,
        "dataset_version": data["schema_version"],
        "dataset_sha256": digest,
        "evaluation_mode": "synthetic_offline",
        "requested": evaluation["requested"],
        "valid_decision_rate": evaluation["valid_decision_rate"],
        "exact_match_rate": evaluation["exact_match_rate"],
        "correct_given_valid_rate": evaluation[
            "correct_given_valid_rate"
        ],
        "failure_counts": dict(sorted(failures.items())),
        "recovery_success": None,
    }
