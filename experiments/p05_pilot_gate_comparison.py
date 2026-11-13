"""Offline comparison using reconstructed P05.13 pilot predictions.

These predictions were transcribed from prior terminal results.
They are NOT an authenticated inference capture.
"""

from pathlib import Path

from agent.diagnosis import Diagnosis
from agent.evidence_gate import gate_diagnosis
from experiments.dataset_loader import load_dataset


PREDICTIONS = (
    ("dependency_failure", "api", "investigate_api"),
    ("dependency_failure", "database", "investigate_database"),
    ("latency", "worker", "investigate_latency"),
    ("dependency_failure", "auth", "investigate_auth"),
    ("unknown", "api", "collect_more_evidence"),
)


def compare():
    cases = load_dataset(
        Path("experiments/datasets/diagnosis_p05_v2.json")
    )

    if len(cases) != len(PREDICTIONS):
        raise ValueError("Pilot case count changed")

    rows = []

    for case, (category, target, action) in zip(cases, PREDICTIONS):
        raw = Diagnosis(
            category=category,
            target=target,
            confidence=0.8,
            summary="Reconstructed pilot prediction; not original model text.",
            recommended_action=action,
        )

        gated = gate_diagnosis(case["signal"], raw)
        expected = case["expected"]

        def exact_match(result):
            return (
                result.category == expected["category"]
                and result.target == expected["target"]
                and result.recommended_action
                == expected["recommended_action"]
            )

        rows.append({
            "case_id": case["case_id"],
            "raw_category": raw.category,
            "gated_category": gated.category,
            "raw_exact_match": exact_match(raw),
            "gated_exact_match": exact_match(gated),
            "downgraded": raw.category != gated.category,
        })

    return {
        "evaluation_mode": "reconstructed_pilot_offline",
        "inference_verified": False,
        "recovery_success": None,
        "requested": len(rows),
        "raw_exact_matches": sum(r["raw_exact_match"] for r in rows),
        "gated_exact_matches": sum(r["gated_exact_match"] for r in rows),
        "downgraded": sum(r["downgraded"] for r in rows),
        "rows": rows,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(compare(), indent=2))
