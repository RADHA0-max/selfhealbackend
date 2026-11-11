"""Deterministic fixture-replay report; no model inference or recovery."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.offline_rpc import OfflineRPC
from experiments.runner import run_experiment
from experiments.scoring import score_results
from testbed.fixtures import build_fixtures


def generate_report() -> dict:
    """Exercise the diagnosis pipeline against known fixture labels."""
    rows = []

    for case in build_fixtures():
        response = json.dumps(
            {
                "category": case.expected_category,
                "target": case.expected_target,
                "confidence": 1.0,
                "summary": "Synthetic fixture replay.",
                "recommended_action": case.expected_action,
            },
            sort_keys=True,
        )

        result = run_experiment((case,), OfflineRPC(response))
        rows.extend(result["results"])

    return {
        "schema_version": 1,
        "evaluation": "fixture_replay",
        "description": (
            "Expected labels replayed through the diagnosis pipeline. "
            "Not a model accuracy benchmark."
        ),
        "model_inference_performed": False,
        "recovery_attempted": False,
        **score_results(rows),
        "results": rows,
    }


def write_report(path: Path) -> dict:
    """Write a deterministic JSON report to an explicit destination."""
    report = generate_report()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return report


if __name__ == "__main__":
    output = Path("experiments/results/fixture_replay.json")
    report = write_report(output)

    print("Report:", output)
    print("Evaluation:", report["evaluation"])
    print("Cases:", report["requested"])
    print("Completed:", report["completed"])
    print("Scores:", report["scores"])
    print("Recovery success:", report["recovery_success"])
