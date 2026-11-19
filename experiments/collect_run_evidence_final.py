"""Bounded, explicit Docker Envoy evidence collection for a completed k6 run.

No workload execution, no container startup, no automatic Docker access.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from experiments.audit_k6_run_final import read_receipt
from experiments.docker_envoy_capture_final import capture_envoy_logs, _validate_window
from experiments.k6_stream_final import extract_k6_manifest
from experiments.k6_snapshot_final import fingerprint, assert_unchanged
from experiments.request_reconciliation_final import reconcile_request_ids
from experiments.traffic_evidence_p15 import TrafficEvidenceError
from experiments.verify_traffic_final import verify

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
CONTAINER = re.compile(r"nanoclaw-[A-Za-z0-9_.-]{1,90}\Z")


def _write_exclusive(path, payload):
    """Create evidence receipt once; never overwrite an existing receipt."""
    encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def prepare(run_id, results_dir):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise TrafficEvidenceError("invalid run ID")

    root = Path(results_dir)
    if root.is_symlink() or not root.is_dir():
        raise TrafficEvidenceError("invalid results directory")

    reservation = root / f"{run_id}.reserved"
    if reservation.is_symlink() or not reservation.is_dir():
        raise TrafficEvidenceError("missing run reservation")

    receipt = read_receipt(reservation / "status.json")
    capture = root / f"{run_id}.jsonl"

    if receipt.get("run_id") != run_id:
        raise TrafficEvidenceError("runner receipt run ID mismatch")
    if receipt.get("status") != "CAPTURE_PARSED":
        raise TrafficEvidenceError("runner capture is not parsed")
    if receipt.get("capture") != str(capture):
        raise TrafficEvidenceError("runner capture path mismatch")

    before_snapshot = fingerprint(capture)
    manifest = extract_k6_manifest(str(capture))
    assert_unchanged(capture, before_snapshot)
    if receipt.get("request_count") != manifest["request_count"]:
        raise TrafficEvidenceError("runner request count mismatch")

    # Validate the complete bounded 60-VU x 20-iteration workload.
    pattern = re.compile(
        rf"{re.escape(run_id)}-organic-vu-"
        r"([1-9][0-9]*)-iter-(0|[1-9][0-9]*)\Z"
    )
    pairs = set()

    for request_id in manifest["request_ids"]:
        match = pattern.fullmatch(request_id)
        if match is None:
            raise TrafficEvidenceError("invalid workload request ID")

        vu = int(match.group(1))
        iteration = int(match.group(2))

        if not 1 <= vu <= 60 or not 0 <= iteration < 20:
            raise TrafficEvidenceError("request outside bounded workload")

        pair = (vu, iteration)
        if pair in pairs:
            raise TrafficEvidenceError("duplicate VU/iteration pair")

        pairs.add(pair)

    evidence_path = reservation / "envoy-evidence.json"
    if evidence_path.exists() or evidence_path.is_symlink():
        raise TrafficEvidenceError("evidence already collected")

    return {
        "run_id": run_id,
        "capture": str(capture),
        "reservation": str(reservation),
        "evidence_path": str(evidence_path),
        "request_count": manifest["request_count"],
        "request_ids": manifest["request_ids"],
        "manifest_sha256": hashlib.sha256(
            manifest["manifest_raw"]
        ).hexdigest(),
        "k6_capture_sha256": before_snapshot["sha256"],
        "k6_capture_snapshot": before_snapshot,
        "scheduled_iterations_complete": len(pairs) == 1200,
        "missing_scheduled_iterations": 1200 - len(pairs),
    }


def collect(
    run_id, results_dir, container, since, until, *,
    require_complete=False,
):
    if not isinstance(container, str) or not CONTAINER.fullmatch(container):
        raise TrafficEvidenceError("invalid Envoy container name")

    _validate_window(since, until)
    prepared = prepare(run_id, results_dir)

    if require_complete and not prepared["scheduled_iterations_complete"]:
        raise TrafficEvidenceError(
            "incomplete workload: "
            f"{prepared['request_count']}/1200 requests"
        )

    report = capture_envoy_logs(
        container,
        since=since,
        until=until,
        expected_request_ids=prepared["request_ids"],
    )

    assert_unchanged(
        prepared["capture"],
        prepared["k6_capture_snapshot"],
    )

    reconciliation = report["request_reconciliation"]
    if not reconciliation["request_ids_match"]:
        raise TrafficEvidenceError("Envoy request IDs do not match k6")

    event_count = report.get("validated_event_count")
    ignored_messages = report.get("ignored_non_json_messages")

    if type(event_count) is not int or event_count != prepared["request_count"]:
        raise TrafficEvidenceError("Envoy event count mismatch")

    if type(ignored_messages) is not int or ignored_messages < 0:
        raise TrafficEvidenceError("invalid ignored Envoy message count")

    # This is a receipt of reconciled records, not proof of complete
    # Docker logs, source-IP isolation, or production recovery.
    receipt = {
        "schema": "nanoclaw.envoy-evidence.final.v1",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "container": container,
        "since": since,
        "until": until,
        "request_count": prepared["request_count"],
        "scheduled_iterations": 1200,
        "scheduled_iterations_complete": prepared[
            "scheduled_iterations_complete"
        ],
        "missing_scheduled_iterations": prepared[
            "missing_scheduled_iterations"
        ],
        "workload_status": (
            "COMPLETE"
            if prepared["scheduled_iterations_complete"]
            else "PARTIAL"
        ),
        "manifest_sha256": prepared["manifest_sha256"],
        "k6_capture_sha256": prepared["k6_capture_sha256"],
        "docker_capture_sha256": report["docker_capture_sha256"],
        "envoy_validated_event_count": report.get(
            "validated_event_count"
        ),
        "envoy_ignored_non_json_messages": report.get(
            "ignored_non_json_messages"
        ),
        "request_ids_match": True,
        "evidence_status": "RECONCILED_UNATTESTED",
        "docker_command_completed": True,
        "capture_completeness_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }

    _write_exclusive(Path(prepared["evidence_path"]), receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(
        description="Explicit bounded Docker Envoy evidence collector"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--results-dir",
        default=str(
            Path(__file__).resolve().parents[1]
            / "testbed/results/final"
        ),
    )
    parser.add_argument("--container", default="nanoclaw-testbed-envoy")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Explicitly permit partial workload evidence",
    )
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Explicitly read Docker logs (never starts containers)",
    )
    args = parser.parse_args()

    try:
        if not args.capture:
            result = prepare(args.run_id, args.results_dir)
            print(json.dumps({
                "status": "READY_NOT_CAPTURED",
                "run_id": args.run_id,
                "request_count": result["request_count"],
                "docker_accessed": False,
            }, sort_keys=True))
            return 0

        if not args.since or not args.until:
            raise TrafficEvidenceError(
                "--since and --until are required with --capture"
            )

        result = collect(
            args.run_id,
            args.results_dir,
            args.container,
            args.since,
            args.until,
            require_complete=not args.allow_partial,
        )
        print(json.dumps({"ok": True, "result": result}, sort_keys=True))
        return 0

    except (TrafficEvidenceError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
