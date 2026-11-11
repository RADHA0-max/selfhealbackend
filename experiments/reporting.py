"""Deterministic metadata for synthetic offline evaluations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any



def fingerprint_responses(responses: dict[str, str]) -> str:
    """Hash canonical predefined responses, including invalid JSON outputs."""
    if not isinstance(responses, dict):
        raise TypeError("responses must be a dictionary")

    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in responses.items()
    ):
        raise TypeError("response keys and values must be strings")

    canonical = json.dumps(
        responses,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()


def build_report(
    dataset_path: Path,
    evaluation: dict[str, Any],
    responses: dict[str, str],
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

    if not isinstance(responses, dict):
        raise TypeError("responses must be a dictionary")

    if set(responses) != set(expected_ids):
        raise ValueError("responses do not match dataset")

    response_sha256 = fingerprint_responses(responses)

    if evaluation.get("mode") != "synthetic_offline":
        raise ValueError("unsupported evaluation mode")

    if evaluation.get("dataset_type") != "synthetic":
        raise ValueError("unsupported dataset type")

    if len(rows) != evaluation["requested"]:
        raise ValueError("result count mismatch")

    if evaluation.get("recovery_success") is not None:
        raise ValueError("offline evaluation cannot claim recovery")

    allowed_statuses = {"ok", "invalid_decision", "agent_error"}
    allowed_reasons = {
        "invalid_json",
        "invalid_schema",
        "transport_error",
        "agent_error",
    }

    actual_counts = Counter()

    for row in rows:
        status = row["status"]
        reason = row["failure_reason"]

        if status not in allowed_statuses:
            raise ValueError("invalid evaluation status")

        if status == "ok":
            if reason is not None:
                raise ValueError("successful row has failure reason")
        elif reason not in allowed_reasons:
            raise ValueError("failed row missing valid failure reason")

        actual_counts[status] += 1

    expected_counts = {
        status: actual_counts[status]
        for status in ("ok", "invalid_decision", "agent_error")
    }

    if evaluation["status_counts"] != expected_counts:
        raise ValueError("evaluation status counts mismatch")

    if evaluation["completed"] != actual_counts["ok"]:
        raise ValueError("evaluation completed count mismatch")

    failures = Counter(
        row["failure_reason"]
        for row in rows
        if row["failure_reason"] is not None
    )

    return {
        "report_version": 1,
        "dataset_version": data["schema_version"],
        "dataset_sha256": digest,
        "responses_sha256": response_sha256,
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
