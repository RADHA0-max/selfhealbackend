"""Offline diagnosis scoring; never claims recovery success."""

from __future__ import annotations

from typing import Any


def score_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score every requested case, including failed diagnoses."""
    total = len(rows)
    metrics = ("category_correct", "target_correct", "action_correct")

    completed = sum(row["status"] == "ok" for row in rows)

    status_counts = {
        "ok": sum(row["status"] == "ok" for row in rows),
        "invalid_decision": sum(
            row["status"] == "invalid_decision" for row in rows
        ),
        "agent_error": sum(
            row["status"] == "agent_error" for row in rows
        ),
    }

    exact_matches = sum(
        row["status"] == "ok"
        and row.get("category_correct") is True
        and row.get("target_correct") is True
        and row.get("action_correct") is True
        for row in rows
    )

    return {
        "requested": total,
        "completed": completed,
        "completion_rate": completed / total if total else None,
        "failure_rate": (total - completed) / total if total else None,
        "exact_match_rate": exact_matches / total if total else None,
        "status_counts": status_counts,
        "scores": {
            metric: (
                sum(row.get(metric) is True for row in rows) / total
                if total else None
            )
            for metric in metrics
        },
        "recovery_success": None,
        "mode": "synthetic_offline",
    }
