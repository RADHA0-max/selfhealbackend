"""Synthetic diagnosis evaluation using an injected offline RPC."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agent.diagnosis import DiagnosisError, diagnose
from experiments.scoring import score_results
from testbed.fixtures import IncidentFixture


def run_experiment(
    cases: tuple[IncidentFixture, ...],
    rpc: Any,
) -> dict[str, Any]:
    """Evaluate diagnoses without executing recovery or contacting Docker."""
    rows = []

    for case in cases:
        row = {
            "case_id": case.case_id,
            "status": "error",
            "category_correct": False,
            "target_correct": False,
            "action_correct": False,
        }

        try:
            result = diagnose(rpc, case.evidence)
        except (DiagnosisError, TimeoutError, ValueError, TypeError):
            row["status"] = "invalid_decision"
        except Exception:
            row["status"] = "agent_error"
        else:
            row.update(
                status="ok",
                category_correct=result.category == case.expected_category,
                target_correct=result.target == case.expected_target,
                action_correct=result.recommended_action == case.expected_action,
                diagnosis=asdict(result),
            )

        rows.append(row)

    return {
        **score_results(rows),
        "results": rows,
    }
