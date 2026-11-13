"""Summarize recorded synthetic diagnosis reliability experiments."""

import json
from pathlib import Path


def summarize_reliability(record):
    """Validate accounting and summarize a recorded diagnosis run."""
    if not isinstance(record, dict):
        raise ValueError("record must be an object")

    if record.get("evaluation_mode") != "recorded_capture_offline":
        raise ValueError("unsupported evaluation mode")

    if record.get("dataset_type") != "synthetic":
        raise ValueError("unsupported dataset type")

    if record.get("inference_verified") is not False:
        raise ValueError("inference must remain unverified")

    if record.get("recovery_success") is not None:
        raise ValueError("recovery must remain unverified")

    requested = record["requested"]
    captured = record["completed"]
    responses = record["partial_responses"]
    failures = record["failures"]
    evaluation = record["evaluation"]

    if type(requested) is not int or requested != 100:
        raise ValueError("expected exactly 100 requested cases")

    if type(captured) is not int or not 0 <= captured <= requested:
        raise ValueError("invalid captured count")

    if not isinstance(responses, dict) or len(responses) != captured:
        raise ValueError("captured response count mismatch")

    if not isinstance(failures, dict):
        raise ValueError("invalid failures")

    rows = evaluation["results"]

    if not isinstance(rows, list) or len(rows) != requested:
        raise ValueError("evaluation row count mismatch")

    case_ids = [row["case_id"] for row in rows]

    if len(set(case_ids)) != requested:
        raise ValueError("duplicate evaluation case IDs")

    expected_ids = set(case_ids)

    if (
        set(responses) & set(failures)
        or set(responses) | set(failures) != expected_ids
    ):
        raise ValueError("response/failure accounting mismatch")

    valid = sum(row["status"] == "ok" for row in rows)

    exact = sum(
        row["status"] == "ok"
        and all(
            row.get(field) is True
            for field in (
                "category_correct",
                "target_correct",
                "action_correct",
            )
        )
        for row in rows
    )

    if evaluation["requested"] != requested:
        raise ValueError("evaluation requested count mismatch")

    if evaluation["completed"] != valid:
        raise ValueError("evaluation valid count mismatch")

    if valid > captured:
        raise ValueError("valid diagnoses exceed captured responses")

    return {
        "report_version": 1,
        "evaluation_mode": "recorded_capture_offline",
        "dataset_type": "synthetic",
        "inference_verified": False,
        "requested": requested,
        "captured_responses": captured,
        "missing_responses": requested - captured,
        "schema_valid_diagnoses": valid,
        "schema_invalid_captured_responses": captured - valid,
        "schema_validity_rate_all_requests": valid / requested,
        "schema_validity_rate_captured": (
            valid / captured if captured else None
        ),
        "exact_matches": exact,
        "exact_match_rate_all_requests": exact / requested,
        "exact_match_rate_valid": exact / valid if valid else None,
        "recovery_success": None,
    }


def summarize_record_file(path):
    """Read a locally recorded run; never contact inference services."""
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    return summarize_reliability(record)
