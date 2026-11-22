#!/usr/bin/env python3
"""Strict offline reconciliation of P01 request evidence."""

import argparse
import json
from collections import Counter
from pathlib import Path


def load_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def require_events(value, label):
    if not isinstance(value, list):
        raise ValueError("{} must be a JSON array".format(label))

    result = []

    for index, event in enumerate(value):
        if not isinstance(event, dict):
            raise ValueError("{}[{}] must be an object".format(label, index))

        run_id = event.get("run_id")
        request_id = event.get("request_id")
        workload = event.get("workload")

        for field, item in (
            ("run_id", run_id),
            ("request_id", request_id),
            ("workload", workload),
        ):
            if not isinstance(item, str) or not item:
                raise ValueError(
                    "{}[{}].{} must be nonempty".format(label, index, field)
                )

        result.append({
            "run_id": run_id,
            "request_id": request_id,
            "workload": workload,
        })

    return result


def measure(expected, observed):
    expected = require_events(expected, "expected")
    observed = require_events(observed, "observed")

    # The complete tuple is the event identity.
    def identity(event):
        return (
            event["run_id"],
            event["request_id"],
            event["workload"],
        )

    expected_counts = Counter(map(identity, expected))
    observed_counts = Counter(map(identity, observed))

    missing = expected_counts - observed_counts
    unexpected = observed_counts - expected_counts

    expected_ids = Counter(e["request_id"] for e in expected)
    observed_ids = Counter(e["request_id"] for e in observed)

    duplicate_expected_ids = sorted(
        key for key, count in expected_ids.items() if count > 1
    )
    duplicate_observed_ids = sorted(
        key for key, count in observed_ids.items() if count > 1
    )

    owners = {}

    for event in expected + observed:
        owners.setdefault(event["request_id"], set()).add(event["run_id"])

    collisions = sorted(
        request_id
        for request_id, run_ids in owners.items()
        if len(run_ids) > 1
    )

    workloads = sorted(
        set(e["workload"] for e in expected + observed)
    )

    by_workload = {}

    for workload in workloads:
        exp = sum(
            count for key, count in expected_counts.items()
            if key[2] == workload
        )
        obs = sum(
            count for key, count in observed_counts.items()
            if key[2] == workload
        )

        by_workload[workload] = {
            "expected": exp,
            "observed": obs,
        }

    passed = (
        not missing
        and not unexpected
        and not duplicate_expected_ids
        and not duplicate_observed_ids
        and not collisions
    )

    def expand(counter):
        return [
            {
                "run_id": key[0],
                "request_id": key[1],
                "workload": key[2],
                "count": count,
            }
            for key, count in sorted(counter.items())
        ]

    return {
        "status": "PASS" if passed else "FAIL",
        "expected_events": len(expected),
        "observed_events": len(observed),
        "matched_events": sum(
            (expected_counts & observed_counts).values()
        ),
        "missing": expand(missing),
        "unexpected": expand(unexpected),
        "duplicate_expected_ids": duplicate_expected_ids,
        "duplicate_observed_ids": duplicate_observed_ids,
        "cross_arm_collisions": collisions,
        "by_workload": by_workload,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", required=True)
    parser.add_argument("--observed", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = measure(
        load_json(args.expected),
        load_json(args.observed),
    )

    output = json.dumps(result, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")

    print(output)

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
