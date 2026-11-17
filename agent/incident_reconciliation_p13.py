"""Bounded, read-only reconciliation of durable offline incident records."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent.measured_audit_p12 import (
    MeasuredAuditError,
    _read_record,
)

MAX_FILES = 2000
RUN_ID = re.compile(r"offline-incident-[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


class IncidentReconciliationError(ValueError):
    """Invalid or inconsistent durable incident state."""


def _check_intent(record: dict[str, Any], run_id: str) -> None:
    if set(record) != {
        "record_version",
        "record_type",
        "run_id",
        "status",
        "automatic_replay_allowed",
    }:
        raise IncidentReconciliationError("invalid intent schema")

    if (
        type(record["record_version"]) is not int
        or record["record_version"] != 1
        or record["record_type"] != "offline_incident_intent"
        or record["run_id"] != run_id
        or record["status"] != "uncertain"
        or record["automatic_replay_allowed"] is not False
    ):
        raise IncidentReconciliationError("invalid incident intent")


def _check_observation(record: dict[str, Any], run_id: str) -> str:
    if set(record) != {
        "record_version",
        "record_type",
        "run_id",
        "result",
        "production_recovery_verified",
    }:
        raise IncidentReconciliationError("invalid observation schema")

    if (
        type(record["record_version"]) is not int
        or record["record_version"] != 1
        or record["record_type"] != "offline_incident_observation"
        or record["run_id"] != run_id
        or record["production_recovery_verified"] is not False
    ):
        raise IncidentReconciliationError("invalid incident observation")

    result = record["result"]

    if type(result) is not dict:
        raise IncidentReconciliationError("invalid observation result")

    if (
        result.get("mitigation_executed") is not False
        or result.get("recovery_attributed_to_agent") is not False
    ):
        raise IncidentReconciliationError("unsupported recovery claim")

    outcome = result.get("observation_outcome")

    if type(outcome) is not str or outcome not in {
        "SUCCESS",
        "FAILED",
        "INCONCLUSIVE",
    }:
        raise IncidentReconciliationError("invalid observation outcome")

    return outcome


def reconcile_offline_incidents(output_dir: str | Path) -> dict[str, Any]:
    """Inventory durable attempts without replaying or modifying them."""

    directory = Path(output_dir) / "offline_incidents"

    summary = {
        "report_version": 1,
        "mode": "read_only_offline_reconciliation",
        "attempted": 0,
        "completed": 0,
        "unresolved": 0,
        "observed_success": 0,
        "observed_failure": 0,
        "inconclusive": 0,
        "automatic_replay_allowed": False,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }

    if directory.is_symlink():
        raise IncidentReconciliationError("symlinked incident directory")

    if not directory.exists():
        return summary

    if not directory.is_dir():
        raise IncidentReconciliationError("invalid incident directory")

    entries = list(directory.iterdir())

    if len(entries) > MAX_FILES:
        raise IncidentReconciliationError("too many incident files")

    intents = {}
    observations = {}

    for path in entries:
        name = path.name

        if not name.startswith("run-") or not name.endswith(".json"):
            raise IncidentReconciliationError("unexpected incident file")

        stem = name[len("run-"):-len(".json")]
        is_intent = stem.endswith("-intent")
        run_id = stem[:-len("-intent")] if is_intent else stem

        if not RUN_ID.fullmatch(run_id):
            raise IncidentReconciliationError("invalid incident filename")

        try:
            record = _read_record(path)
        except MeasuredAuditError as exc:
            raise IncidentReconciliationError("invalid incident file") from exc

        if is_intent:
            _check_intent(record, run_id)
            if run_id in intents:
                raise IncidentReconciliationError("duplicate intent")
            intents[run_id] = record
        else:
            outcome = _check_observation(record, run_id)
            if run_id in observations:
                raise IncidentReconciliationError("duplicate observation")
            observations[run_id] = outcome

    if not observations.keys() <= intents.keys():
        raise IncidentReconciliationError("observation without intent")

    summary["attempted"] = len(intents)
    summary["completed"] = len(observations)
    summary["unresolved"] = len(intents) - len(observations)

    for outcome in observations.values():
        if outcome == "SUCCESS":
            summary["observed_success"] += 1
        elif outcome == "FAILED":
            summary["observed_failure"] += 1
        else:
            summary["inconclusive"] += 1

    return summary
