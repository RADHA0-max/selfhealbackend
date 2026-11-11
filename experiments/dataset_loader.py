"""Strict loader for versioned synthetic diagnosis datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.diagnosis import (
    ALLOWED_ACTIONS,
    ALLOWED_CATEGORIES,
    ALLOWED_TARGETS,
)
from agent.signal_adapter import signal_to_evidence


class DatasetValidationError(ValueError):
    """Invalid or unsupported evaluation dataset."""


def validate_dataset(data: Any) -> tuple[dict, ...]:
    if not isinstance(data, dict):
        raise DatasetValidationError("dataset must be an object")

    if set(data) != {"schema_version", "dataset_type", "cases"}:
        raise DatasetValidationError("unexpected dataset fields")

    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise DatasetValidationError("unsupported schema version")

    if data["dataset_type"] != "synthetic":
        raise DatasetValidationError("unsupported dataset type")

    cases = data["cases"]

    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
        raise DatasetValidationError("invalid case count")

    seen = set()
    validated = []

    for case in cases:
        if not isinstance(case, dict):
            raise DatasetValidationError("case must be an object")

        if set(case) != {"case_id", "signal", "expected"}:
            raise DatasetValidationError("unexpected case fields")

        case_id = case["case_id"]

        if not isinstance(case_id, str) or not case_id:
            raise DatasetValidationError("invalid case ID")

        if case_id in seen:
            raise DatasetValidationError("duplicate case ID")

        seen.add(case_id)

        try:
            signal_to_evidence(case["signal"])
        except (ValueError, TypeError) as exc:
            raise DatasetValidationError("invalid signal") from exc

        if case["signal"]["signal_id"] != case_id:
            raise DatasetValidationError("signal ID mismatch")

        expected = case["expected"]

        if not isinstance(expected, dict):
            raise DatasetValidationError("expected labels must be an object")

        if set(expected) != {
            "category",
            "target",
            "recommended_action",
        }:
            raise DatasetValidationError("unexpected expected fields")

        for field, allowed in (
            ("category", ALLOWED_CATEGORIES),
            ("target", ALLOWED_TARGETS),
            ("recommended_action", ALLOWED_ACTIONS),
        ):
            value = expected[field]

            if not isinstance(value, str) or value not in allowed:
                raise DatasetValidationError(f"invalid expected {field}")

        validated.append(case)

    return tuple(validated)


def load_dataset(path: Path) -> tuple[dict, ...]:
    """Load a bounded JSON dataset with strict duplicate-key rejection."""
    if path.stat().st_size > 1024 * 1024:
        raise DatasetValidationError("dataset exceeds 1 MiB")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DatasetValidationError("duplicate JSON field")
            result[key] = value
        return result

    data = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_pairs,
    )

    return validate_dataset(data)
