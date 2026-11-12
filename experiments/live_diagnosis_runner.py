"""Bounded diagnosis capture through an injected RPC transport.

No CLI or live endpoint is exposed. Callers must explicitly supply transport.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from agent.diagnosis import diagnose
from agent.signal_adapter import signal_to_evidence
from experiments.dataset_loader import validate_dataset
from experiments.response_capture import (
    MAX_RESPONSE_BYTES,
    validate_capture,
)


MAX_CASES = 100


class CaptureRunError(ValueError):
    """Invalid capture configuration or incomplete inference run."""


class RecordingRPC:
    """Record raw broker content while reusing the production diagnosis path."""

    def __init__(self, transport: Any) -> None:
        self.transport = transport
        self.raw_content = None

    def call(self, model, messages, *, max_tokens=256, temperature=0.0):
        response = self.transport.call(
            model,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if isinstance(response, dict) and response.get("ok") is True:
            self.raw_content = response.get("content")
        return response


def capture_diagnoses(
    dataset: dict[str, Any],
    transport: Any,
    *,
    model_id: str,
    run_id: str,
    checkpoint: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Capture at most 100 cases; never execute recommended actions."""
    cases = validate_dataset(dataset)

    if len(cases) > MAX_CASES:
        raise CaptureRunError("run exceeds 100 cases")

    if checkpoint is not None and any(
        len(case["case_id"]) > 56
        or case["case_id"].endswith("-outcome")
        for case in cases
    ):
        raise CaptureRunError("invalid checkpoint case ID")

    # Validate metadata before publishing any requests.
    placeholder = {
        "schema_version": 1,
        "capture_source": "model_inference",
        "model_id": model_id,
        "run_id": run_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "responses": {case["case_id"]: "" for case in cases},
    }
    validate_capture(placeholder, dataset)

    responses = {}
    failures = {}

    for case in cases:
        case_id = case["case_id"]
        recorder = RecordingRPC(transport)

        # Persist intent before any request can reach the transport.
        if checkpoint is not None:
            checkpoint(case_id, status="uncertain")

        try:
            evidence = signal_to_evidence(case["signal"])
            diagnose(recorder, evidence)
        except Exception as exc:
            failures[case_id] = type(exc).__name__

        raw = recorder.raw_content

        if isinstance(raw, str):
            if len(raw.encode("utf-8")) <= MAX_RESPONSE_BYTES:
                responses[case_id] = raw
            else:
                failures[case_id] = "response_too_large"
        else:
            failures.setdefault(case_id, "missing_model_content")

        if checkpoint is not None:
            if case_id in responses:
                checkpoint(
                    case_id + "-outcome",
                    status="completed",
                    response=responses[case_id],
                )
            else:
                checkpoint(
                    case_id + "-outcome",
                    status="failed",
                    error=failures.get(case_id, "unknown_failure"),
                )

    capture = dict(placeholder)
    capture["responses"] = responses

    complete = len(responses) == len(cases)

    if complete:
        validate_capture(capture, dataset)

    return {
        "capture": capture if complete else None,
        "partial_responses": dict(responses),
        "completed": len(responses),
        "requested": len(cases),
        "failures": failures,
        "inference_verified": False,
        "recovery_success": None,
    }
