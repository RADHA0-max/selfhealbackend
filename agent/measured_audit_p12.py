"""Read-only, fail-closed audit of P11 measured incident receipts.

Checks local record consistency, not observer authenticity or causality.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from agent.measured_incident_p10 import (
    MAX_REPORT_BYTES,
    load_measured_report,
)
from chaos.recovery_timeline import evaluate_timeline


MAX_RECORD_BYTES = 1024 * 1024
MAX_RECEIPTS = 1000
EXPERIMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,61}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
OUTCOMES = frozenset({"SUCCESS", "FAILED", "INCONCLUSIVE"})

RECEIPT_KEYS = frozenset({
    "receipt_version",
    "incident_sha256",
    "experiment_id",
    "evidence_sha256",
    "evidence_source",
    "required_healthy",
    "observed_sustained_recovery",
    "uninterrupted_recovery",
    "incident_run_id",
    "mitigation_executed",
    "recovery_attributed_to_agent",
    "production_recovery_verified",
})

INCIDENT_KEYS = frozenset({
    "record_version",
    "record_type",
    "run_id",
    "result",
    "production_recovery_verified",
})

INTENT_KEYS = frozenset({
    "record_version",
    "record_type",
    "run_id",
    "status",
    "automatic_replay_allowed",
})


class MeasuredAuditError(ValueError):
    """Invalid, incomplete, or inconsistent local audit records."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MeasuredAuditError("duplicate JSON key")
        result[key] = value
    return result


def _read_record(path: Path) -> dict[str, Any]:
    """Read a bounded regular file without following its final symlink."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())

            if not stat.S_ISREG(metadata.st_mode):
                raise MeasuredAuditError("record is not a regular file")

            if metadata.st_size > MAX_RECORD_BYTES:
                raise MeasuredAuditError("record exceeds size limit")

            raw = stream.read(MAX_RECORD_BYTES + 1)

        if len(raw) > MAX_RECORD_BYTES:
            raise MeasuredAuditError("record exceeds size limit")

        record = json.loads(
            raw,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                MeasuredAuditError("nonfinite JSON value")
            ),
        )
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        raise MeasuredAuditError("invalid audit record") from exc

    if type(record) is not dict:
        raise MeasuredAuditError("audit record must be an object")

    return record


def _canonical_hash(record: dict[str, Any]) -> str:
    try:
        raw = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise MeasuredAuditError("invalid canonical record") from exc

    return hashlib.sha256(raw).hexdigest()


def _check_false_claims(record, fields):
    for field in fields:
        if record.get(field) is not False:
            raise MeasuredAuditError(f"unsupported claim: {field}")


def _validate_receipt(receipt, path):
    if set(receipt) != RECEIPT_KEYS:
        raise MeasuredAuditError("unsupported receipt schema")

    experiment_id = receipt["experiment_id"]

    if type(experiment_id) is not str or not EXPERIMENT_ID.fullmatch(
        experiment_id
    ):
        raise MeasuredAuditError("invalid experiment ID")

    if path.name != f"run-measured-receipt-{experiment_id}.json":
        raise MeasuredAuditError("receipt filename mismatch")

    if type(receipt["receipt_version"]) is not int or (
        receipt["receipt_version"] != 1
    ):
        raise MeasuredAuditError("unsupported receipt version")

    if receipt["evidence_source"] != "isolated_envoy_http":
        raise MeasuredAuditError("unsupported evidence source")

    for field in ("incident_sha256", "evidence_sha256"):
        value = receipt[field]
        if type(value) is not str or not SHA256.fullmatch(value):
            raise MeasuredAuditError("invalid evidence fingerprint")

    threshold = receipt["required_healthy"]
    if type(threshold) is not int or not 2 <= threshold <= 10:
        raise MeasuredAuditError("invalid recovery threshold")

    for field in (
        "observed_sustained_recovery",
        "uninterrupted_recovery",
    ):
        if type(receipt[field]) is not str or receipt[field] not in OUTCOMES:
            raise MeasuredAuditError("invalid recovery outcome")

    expected_run_id = f"offline-incident-{experiment_id}-0"
    if receipt["incident_run_id"] != expected_run_id:
        raise MeasuredAuditError("incident linkage mismatch")

    _check_false_claims(
        receipt,
        (
            "mitigation_executed",
            "recovery_attributed_to_agent",
            "production_recovery_verified",
        ),
    )


def _validate_incident(incident, intent, receipt):
    run_id = receipt["incident_run_id"]

    if set(incident) != INCIDENT_KEYS:
        raise MeasuredAuditError("unsupported incident schema")

    if (
        type(incident["record_version"]) is not int
        or incident["record_version"] != 1
        or incident["record_type"] != "offline_incident_observation"
        or incident["run_id"] != run_id
    ):
        raise MeasuredAuditError("invalid incident record")

    if incident["production_recovery_verified"] is not False:
        raise MeasuredAuditError("unsupported production claim")

    result = incident["result"]
    if type(result) is not dict:
        raise MeasuredAuditError("invalid incident result")

    if result.get("observation_outcome") != receipt["uninterrupted_recovery"]:
        raise MeasuredAuditError("conservative outcome mismatch")

    _check_false_claims(
        result,
        ("mitigation_executed", "recovery_attributed_to_agent"),
    )

    if _canonical_hash(incident) != receipt["incident_sha256"]:
        raise MeasuredAuditError("incident fingerprint mismatch")

    if set(intent) != INTENT_KEYS:
        raise MeasuredAuditError("unsupported intent schema")

    if (
        type(intent["record_version"]) is not int
        or intent["record_version"] != 1
        or intent["record_type"] != "offline_incident_intent"
        or intent["run_id"] != run_id
        or intent["status"] != "uncertain"
        or intent["automatic_replay_allowed"] is not False
    ):
        raise MeasuredAuditError("invalid incident intent")


def _read_evidence(path: Path) -> bytes:
    """Read bounded evidence bytes without following final symlinks."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())

            if not stat.S_ISREG(metadata.st_mode):
                raise MeasuredAuditError("invalid evidence file")

            if metadata.st_size > MAX_REPORT_BYTES:
                raise MeasuredAuditError("evidence exceeds size limit")

            raw = stream.read(MAX_REPORT_BYTES + 1)

    except OSError as exc:
        raise MeasuredAuditError("cannot read evidence") from exc

    if len(raw) > MAX_REPORT_BYTES:
        raise MeasuredAuditError("evidence exceeds size limit")

    return raw


def audit_measured_receipts(
    output_dir: str | Path,
    *,
    evidence_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Audit P11 receipts without RPC, mutation, or external requests."""

    root = Path(output_dir)
    receipt_dir = root / "measured_receipts"
    incident_dir = root / "offline_incidents"

    summary = {
        "audit_version": 1,
        "mode": "local_record_consistency",
        "receipts_verified": 0,
        "evidence_files_verified": 0,
        "observed_success": 0,
        "observed_failure": 0,
        "observed_inconclusive": 0,
        "uninterrupted_success": 0,
        "uninterrupted_failure": 0,
        "uninterrupted_inconclusive": 0,
        "observer_authenticated": False,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }

    if receipt_dir.is_symlink():
        raise MeasuredAuditError("symlinked receipt directory")

    if not receipt_dir.exists():
        return summary

    if not receipt_dir.is_dir():
        raise MeasuredAuditError("invalid receipt directory")

    if incident_dir.is_symlink() or not incident_dir.is_dir():
        raise MeasuredAuditError("invalid incident directory")

    # Inspect every entry, not only matching names, to fail closed.
    entries = list(receipt_dir.iterdir())

    if len(entries) > MAX_RECEIPTS:
        raise MeasuredAuditError("too many receipt records")

    seen = set()

    for path in sorted(entries):
        if not path.name.startswith("run-measured-receipt-") or (
            not path.name.endswith(".json")
        ):
            raise MeasuredAuditError("unexpected receipt directory entry")

        receipt = _read_record(path)
        _validate_receipt(receipt, path)

        experiment_id = receipt["experiment_id"]
        if experiment_id in seen:
            raise MeasuredAuditError("duplicate experiment")
        seen.add(experiment_id)

        run_id = receipt["incident_run_id"]

        incident_path = incident_dir / f"run-{run_id}.json"
        intent_path = incident_dir / f"run-{run_id}-intent.json"

        incident = _read_record(incident_path)
        intent = _read_record(intent_path)

        _validate_incident(incident, intent, receipt)

        if evidence_dir is not None:
            evidence_root = Path(evidence_dir)

            if evidence_root.is_symlink() or not evidence_root.is_dir():
                raise MeasuredAuditError("invalid evidence directory")

            evidence_path = evidence_root / f"{experiment_id}.json"

            # Read the exact bytes used for the fingerprint.
            evidence = _read_evidence(evidence_path)

            if hashlib.sha256(evidence).hexdigest() != receipt["evidence_sha256"]:
                raise MeasuredAuditError("evidence fingerprint mismatch")

            # Validate the exact bytes that passed the SHA-256 check.
            # Never reopen the original evidence during validation.
            with tempfile.TemporaryDirectory(
                prefix="nanoclaw-p12-audit-"
            ) as temporary:
                snapshot = Path(temporary) / evidence_path.name
                snapshot.write_bytes(evidence)
                report = load_measured_report(snapshot)

            expected = evaluate_timeline(
                report["events"],
                required_healthy=receipt["required_healthy"],
                healthy_latency_ms=report["healthy_latency_ms"],
            )

            if expected["observation_outcome"] != (
                receipt["observed_sustained_recovery"]
            ):
                raise MeasuredAuditError("observed recovery mismatch")

            summary["evidence_files_verified"] += 1

        summary["receipts_verified"] += 1

        outcome_suffix = {
            "SUCCESS": "success",
            "FAILED": "failure",
            "INCONCLUSIVE": "inconclusive",
        }

        observed = outcome_suffix[
            receipt["observed_sustained_recovery"]
        ]
        conservative = outcome_suffix[
            receipt["uninterrupted_recovery"]
        ]

        summary[f"observed_{observed}"] += 1
        summary[f"uninterrupted_{conservative}"] += 1

    # Detect completed P10-style measured incidents missing P11 receipts.
    # A matching intent and completed observation are both required.
    measured_prefix = "run-offline-incident-"

    for path in incident_dir.iterdir():
        name = path.name

        if not name.startswith(measured_prefix):
            continue

        if not name.endswith("-0.json"):
            continue

        experiment_id = name[
            len(measured_prefix):-len("-0.json")
        ]

        if not EXPERIMENT_ID.fullmatch(experiment_id):
            continue

        run_id = f"offline-incident-{experiment_id}-0"
        intent_path = incident_dir / f"run-{run_id}-intent.json"

        if not intent_path.is_file():
            continue

        # Only classify completed records with matching P10-style intent.
        incident = _read_record(path)
        intent = _read_record(intent_path)

        if (
            incident.get("record_type") == "offline_incident_observation"
            and incident.get("run_id") == run_id
            and intent.get("record_type") == "offline_incident_intent"
            and intent.get("run_id") == run_id
            and experiment_id not in seen
        ):
            raise MeasuredAuditError(
                "completed measured incident missing receipt"
            )

    return summary
