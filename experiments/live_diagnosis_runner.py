"""Bounded diagnosis capture through an injected RPC transport.

No CLI or live endpoint is exposed. Callers must explicitly supply transport.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
) -> dict[str, Any]:
    """Capture at most 100 cases; never execute recommended actions."""
    cases = validate_dataset(dataset)

    if len(cases) > MAX_CASES:
        raise CaptureRunError("run exceeds 100 cases")

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
