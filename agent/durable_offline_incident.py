"""Replay-safe, advisory-only offline incident evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.offline_incident import evaluate_sustained_offline_incident
from agent.recovery_verification import verify_sustained_recovery
from experiments.run_record import RunRecordError, write_run_record
from experiments.run_reservation import reserve_run


class IncidentReplayError(RuntimeError):
    """Incident has already been attempted or reserved."""


def evaluate_durable_offline_incident(
    rpc: Any,
    before: dict[str, Any],
    observations: list[dict[str, Any]],
    output_dir: str | Path,
    required_healthy: int = 3,
) -> dict[str, Any]:
    """Persist intent before RPC and prevent automatic replay."""

    # Validate all evidence before creating any durable state.
    verify_sustained_recovery(before, observations, required_healthy)

    incident_id = before["signal_id"]
    run_id = "offline-incident-" + incident_id

    directory = Path(output_dir) / "offline_incidents"
    directory.mkdir(parents=True, exist_ok=True)

    with reserve_run(directory, run_id):
        intent = {
            "record_version": 1,
            "record_type": "offline_incident_intent",
            "run_id": run_id,
            "status": "uncertain",
            "automatic_replay_allowed": False,
        }

        # Immutable creation: this file survives exceptions and crashes.
        # An existing intent means the incident must not be replayed.
        try:
            write_run_record(
                directory,
                run_id + "-intent",
                intent,
            )
        except (FileExistsError, RunRecordError) as exc:
            raise IncidentReplayError(
                "incident already attempted; automatic replay prohibited"
            ) from exc

        result = evaluate_sustained_offline_incident(
            rpc, before, observations, required_healthy
        )

        record = {
            "record_version": 1,
            "record_type": "offline_incident_observation",
            "run_id": run_id,
            "result": result,
            "production_recovery_verified": False,
        }

        write_run_record(directory, run_id, record)

    return record
