"""Offline diagnosis scoring; never claims recovery success."""

from __future__ import annotations

from typing import Any


def score_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score every requested case, including failed diagnoses."""
    total = len(rows)
    metrics = ("category_correct", "target_correct", "action_correct")

    return {
        "requested": total,
        "completed": sum(row["status"] == "ok" for row in rows),
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
