"""Run a bounded, sequential diagnosis reliability experiment."""

from pathlib import Path

from experiments.rate_limited_transport_p06 import RateLimitedTransport
from experiments.recorded_diagnosis_run import run_and_record
from experiments.reliability_dataset_p06 import build_reliability_dataset


def run_reliability_experiment(
    transport,
    *,
    model_id,
    run_id,
    output_dir,
    interval_seconds=2.0,
    clock=None,
    sleep=None,
):
    """Record exactly 100 synthetic diagnosis attempts, without retries."""
    dataset = build_reliability_dataset()

    if len(dataset["cases"]) != 100:
        raise ValueError("reliability experiment requires 100 cases")

    options = {"interval_seconds": interval_seconds}

    if clock is not None:
        options["clock"] = clock

    if sleep is not None:
        options["sleep"] = sleep

    limited = RateLimitedTransport(transport, **options)

    return run_and_record(
        dataset,
        limited,
        model_id=model_id,
        run_id=run_id,
        output_dir=Path(output_dir),
    )
