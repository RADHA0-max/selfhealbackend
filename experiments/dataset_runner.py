"""Evaluate synthetic datasets through the validated signal path.

Offline only: no mitigation, live model inference, or recovery verification.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agent.diagnosis import DiagnosisError
from agent.signal_diagnosis import diagnose_signal
from experiments.dataset_loader import validate_dataset
from experiments.failure_classification import classify_failure
from experiments.offline_rpc import OfflineRPC
from experiments.scoring import score_results


def run_dataset(
    dataset: dict[str, Any],
    responses: dict[str, str],
) -> dict[str, Any]:
    """Score independently labeled cases against predefined model responses."""
    cases = validate_dataset(dataset)

    if not isinstance(responses, dict):
        raise TypeError("responses must be a mapping")

    if set(responses) != {case["case_id"] for case in cases}:
        raise ValueError("response IDs must match dataset case IDs")

    if any(not isinstance(value, str) for value in responses.values()):
        raise TypeError("responses must contain strings")

    rows = []

    for case in cases:
        case_id = case["case_id"]
        expected = case["expected"]

        row = {
            "case_id": case_id,
            "status": "error",
            "failure_reason": None,
            "category_correct": False,
            "target_correct": False,
            "action_correct": False,
        }

        try:
            result = diagnose_signal(
                OfflineRPC(responses[case_id]),
                case["signal"],
            )
        except (DiagnosisError, TimeoutError, ValueError, TypeError) as exc:
            row["status"] = "invalid_decision"
            row["failure_reason"] = classify_failure(exc)
        except Exception as exc:
            row["status"] = "agent_error"
            row["failure_reason"] = classify_failure(exc)
        else:
            row.update(
                status="ok",
                category_correct=result.category == expected["category"],
                target_correct=result.target == expected["target"],
                action_correct=(
                    result.recommended_action
                    == expected["recommended_action"]
                ),
                diagnosis=asdict(result),
            )

        rows.append(row)

    return {
        **score_results(rows),
        "dataset_type": "synthetic",
        "results": rows,
    }
