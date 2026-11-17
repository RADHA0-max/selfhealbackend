"""Immutable advisory receipt for a validated, measured offline incident.

Does not authenticate the observer, execute mitigation, or prove causality.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from agent.measured_incident_p10 import (
    MAX_REPORT_BYTES,
    MeasuredIncidentError,
    evaluate_measured_incident,
    load_measured_report,
)
from chaos.recovery_timeline import evaluate_timeline
from experiments.run_record import write_run_record


class MeasuredReceiptError(ValueError):
    """Invalid measured receipt request or evidence."""


def evaluate_measured_receipt(
    rpc: Any,
    report_path: str | Path,
    output_dir: str | Path,
    *,
    required_healthy: int = 3,
) -> dict[str, Any]:
    """Evaluate measured evidence once and persist an immutable receipt."""

    if type(required_healthy) is not int or not 2 <= required_healthy <= 10:
        raise MeasuredReceiptError("required_healthy must be 2..10")

    path = Path(report_path)

    # Read the evidence exactly once, without following symlinks.
    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise MeasuredReceiptError("evidence must be a regular file")
            raw = stream.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        raise MeasuredReceiptError("cannot read evidence") from exc

    if len(raw) > MAX_REPORT_BYTES:
        raise MeasuredReceiptError("evidence exceeds size limit")

    fingerprint = hashlib.sha256(raw).hexdigest()

    # Use a private snapshot for validation and diagnosis.
    # The snapshot has the expected experiment filename.
    with tempfile.TemporaryDirectory(prefix="nanoclaw-p11-") as snapshot_dir:
        try:
            metadata = json.loads(raw)
            experiment_id = metadata["experiment_id"]
        except (ValueError, TypeError, KeyError) as exc:
            raise MeasuredReceiptError("invalid evidence metadata") from exc

        if type(experiment_id) is not str:
            raise MeasuredReceiptError("invalid experiment ID")

        # Validate the original filename before snapshot creation.
        if path.name != experiment_id + ".json":
            raise MeasuredReceiptError("evidence filename mismatch")

        # Prevent path traversal and unsupported names.
        if not experiment_id.isascii() or not all(
            char.isalnum() or char in "_-" for char in experiment_id
        ):
            raise MeasuredReceiptError("invalid experiment ID")

        snapshot = Path(snapshot_dir) / path.name
        snapshot.write_bytes(raw)

        report = load_measured_report(snapshot)

        if len(report["events"]) - 1 < required_healthy:
            raise MeasuredReceiptError("insufficient recovery observations")

        timeline = evaluate_timeline(
            report["events"],
            required_healthy=required_healthy,
            healthy_latency_ms=report["healthy_latency_ms"],
        )

        incident = evaluate_measured_incident(
            rpc,
            snapshot,
            output_dir,
            required_healthy=required_healthy,
        )

    # Bind the receipt to the exact persisted incident result.
    incident_bytes = json.dumps(
        incident["incident_record"],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    incident_hash = hashlib.sha256(incident_bytes).hexdigest()

    receipt = {
        "receipt_version": 1,
        "incident_sha256": incident_hash,
        "experiment_id": report["experiment_id"],
        "evidence_sha256": fingerprint,
        "evidence_source": "isolated_envoy_http",
        "required_healthy": required_healthy,
        "observed_sustained_recovery": timeline["observation_outcome"],
        "uninterrupted_recovery": incident["uninterrupted_recovery"],
        "incident_run_id": incident["incident_record"]["run_id"],
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }

    directory = Path(output_dir) / "measured_receipts"
    directory.mkdir(parents=True, exist_ok=True)

    write_run_record(
        directory,
        "measured-receipt-" + report["experiment_id"],
        receipt,
    )

    return receipt
