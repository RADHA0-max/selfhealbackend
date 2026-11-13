"""Construct a bounded, repeated synthetic diagnosis reliability dataset."""

from copy import deepcopy
from pathlib import Path

from experiments.dataset_loader import load_dataset, validate_dataset


SOURCE = Path("experiments/datasets/diagnosis_p05_v2.json")
REPEATS = 20
EXPECTED_CASES = 100


def build_reliability_dataset():
    source_cases = load_dataset(SOURCE)

    if len(source_cases) != 5:
        raise ValueError("expected exactly five source cases")

    cases = []

    for repeat in range(REPEATS):
        for source in source_cases:
            case = deepcopy(source)
            case_id = "{}-r{:02d}".format(
                source["case_id"],
                repeat + 1,
            )

            case["case_id"] = case_id
            case["signal"]["signal_id"] = case_id
            cases.append(case)

    dataset = {
        "schema_version": 1,
        "dataset_type": "synthetic",
        "cases": cases,
    }

    validate_dataset(dataset)

    if len(cases) != EXPECTED_CASES:
        raise ValueError("reliability dataset must contain 100 cases")

    return dataset
