"""Validate externally captured diagnosis responses.

This module validates structure, not the authenticity of model inference.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.dataset_loader import validate_dataset


MAX_CAPTURE_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}")


class CaptureValidationError(ValueError):
    """Invalid or unsupported response capture."""


def _unique_pairs(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise CaptureValidationError("duplicate JSON field")
        result[key] = value

    return result


def validate_capture(
    capture: Any,
    dataset: dict[str, Any],
) -> dict[str, str]:
    """Return validated responses indexed by dataset case ID."""
    cases = validate_dataset(dataset)

    if not isinstance(capture, dict):
        raise CaptureValidationError("capture must be an object")

    required = {
        "schema_version",
        "capture_source",
        "model_id",
        "run_id",
        "captured_at",
        "responses",
    }

    if set(capture) != required:
        raise CaptureValidationError("unexpected capture fields")

    if type(capture["schema_version"]) is not int:
        raise CaptureValidationError("invalid capture version")

    if capture["schema_version"] != 1:
        raise CaptureValidationError("unsupported capture version")

    if capture["capture_source"] != "model_inference":
        raise CaptureValidationError("unsupported capture source")

    for field in ("model_id", "run_id"):
        value = capture[field]

        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise CaptureValidationError(f"invalid {field}")

    timestamp = capture["captured_at"]

    if not isinstance(timestamp, str) or len(timestamp) > 40:
        raise CaptureValidationError("invalid capture timestamp")

    try:
        parsed = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise CaptureValidationError("invalid capture timestamp") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CaptureValidationError("timestamp must include timezone")

    responses = capture["responses"]

    if not isinstance(responses, dict):
        raise CaptureValidationError("responses must be an object")

    expected_ids = {case["case_id"] for case in cases}

    if set(responses) != expected_ids:
        raise CaptureValidationError("response IDs must match dataset")

    for response in responses.values():
        if not isinstance(response, str):
            raise CaptureValidationError("response must be a string")

        if len(response.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise CaptureValidationError("response exceeds size limit")

    return dict(responses)


def load_capture(
    path: Path,
    dataset: dict[str, Any],
) -> dict[str, str]:
    """Load a bounded capture file, rejecting duplicate JSON keys."""
    if path.stat().st_size > MAX_CAPTURE_BYTES:
        raise CaptureValidationError("capture exceeds size limit")

    capture = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_pairs,
        parse_constant=lambda value: (
            _reject_constant(value)
        ),
    )

    return validate_capture(capture, dataset)


def _reject_constant(value):
    raise CaptureValidationError(f"invalid JSON constant: {value}")
