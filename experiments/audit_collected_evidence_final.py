"""Read-only integrity audit of collected k6/Envoy evidence receipts.

This validates recorded evidence consistency. It does not authenticate
Docker runtime origin, source IPs, or production recovery.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from experiments.audit_k6_run_final import read_receipt
from experiments.collect_run_evidence_final import prepare
from experiments.k6_snapshot_final import assert_unchanged
from experiments.traffic_evidence_p15 import TrafficEvidenceError

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def audit_collected(run_id, results_dir, *, allow_partial=False):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise TrafficEvidenceError("invalid run ID")

    root = Path(results_dir)

    if root.is_symlink() or not root.is_dir():
        raise TrafficEvidenceError("invalid results directory")

    reservation = root / f"{run_id}.reserved"

    if reservation.is_symlink() or not reservation.is_dir():
        raise TrafficEvidenceError("missing run reservation")

    evidence_path = reservation / "envoy-evidence.json"

    # Read the receipt first. prepare() intentionally refuses an existing
    # evidence receipt, so validate the underlying runner evidence using
    # a separate read-only path below.
    evidence = read_receipt(evidence_path)

    required = {
        "schema",
        "run_id",
        "request_count",
        "manifest_sha256",
        "k6_capture_sha256",
        "docker_capture_sha256",
        "request_ids_match",
        "evidence_status",
        "workload_status",
        "scheduled_iterations_complete",
        "capture_completeness_verified",
        "runtime_origin_verified",
        "source_ip_verified",
        "production_recovery_verified",
    }

    if not required.issubset(evidence):
        raise TrafficEvidenceError("incomplete evidence receipt")

    if evidence["schema"] != "nanoclaw.envoy-evidence.final.v1":
        raise TrafficEvidenceError("unsupported evidence schema")

    if evidence["run_id"] != run_id:
        raise TrafficEvidenceError("evidence run ID mismatch")

    if evidence["request_ids_match"] is not True:
        raise TrafficEvidenceError("evidence is not reconciled")

    if evidence["evidence_status"] != "RECONCILED_UNATTESTED":
        raise TrafficEvidenceError("invalid evidence status")

    for field in (
        "capture_completeness_verified",
        "runtime_origin_verified",
        "source_ip_verified",
        "production_recovery_verified",
    ):
        if evidence[field] is not False:
            raise TrafficEvidenceError(
                "unsupported provenance claim: " + field
            )

    for field in (
        "manifest_sha256",
        "k6_capture_sha256",
        "docker_capture_sha256",
    ):
        value = evidence[field]
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            raise TrafficEvidenceError("invalid digest: " + field)

    runner = read_receipt(reservation / "status.json")

    capture = root / f"{run_id}.jsonl"

    if runner.get("run_id") != run_id:
        raise TrafficEvidenceError("runner ID mismatch")

    if runner.get("status") != "CAPTURE_PARSED":
        raise TrafficEvidenceError("runner status mismatch")

    if runner.get("capture") != str(capture):
        raise TrafficEvidenceError("runner capture mismatch")

    # Recompute the manifest using the existing bounded streaming parser.
    from experiments.k6_stream_final import extract_k6_manifest
    from experiments.k6_snapshot_final import fingerprint

    before = fingerprint(capture)
    manifest = extract_k6_manifest(str(capture))
    assert_unchanged(capture, before)

    if evidence["k6_capture_sha256"] != before["sha256"]:
        raise TrafficEvidenceError("k6 capture digest mismatch")

    actual_manifest_digest = hashlib.sha256(
        manifest["manifest_raw"]
    ).hexdigest()

    if evidence["manifest_sha256"] != actual_manifest_digest:
        raise TrafficEvidenceError("k6 manifest digest mismatch")

    count = manifest["request_count"]

    if (
        type(evidence["request_count"]) is not int
        or type(runner.get("request_count")) is not int
        or evidence["request_count"] != count
        or runner["request_count"] != count
    ):
        raise TrafficEvidenceError("request count mismatch")

    # Validate the actual VU/iteration namespace, not just the count.
    pattern = re.compile(
        rf"{re.escape(run_id)}-organic-vu-"
        r"([1-9][0-9]*)-iter-(0|[1-9][0-9]*)\Z"
    )

    pairs = set()

    for request_id in manifest["request_ids"]:
        match = pattern.fullmatch(request_id)

        if match is None:
            raise TrafficEvidenceError("invalid request ID namespace")

        vu, iteration = map(int, match.groups())

        if not (1 <= vu <= 60 and 0 <= iteration < 20):
            raise TrafficEvidenceError("request outside workload bounds")

        pair = (vu, iteration)

        if pair in pairs:
            raise TrafficEvidenceError("duplicate workload iteration")

        pairs.add(pair)

    complete = len(pairs) == 1200
    expected_status = "COMPLETE" if complete else "PARTIAL"

    if evidence["workload_status"] != expected_status:
        raise TrafficEvidenceError("workload status mismatch")

    if evidence["scheduled_iterations_complete"] is not complete:
        raise TrafficEvidenceError("completion flag mismatch")

    if not complete and not allow_partial:
        raise TrafficEvidenceError(
            f"incomplete workload: {len(pairs)}/1200"
        )

    assert_unchanged(capture, before)

    event_count = evidence.get("envoy_validated_event_count")
    ignored_messages = evidence.get("envoy_ignored_non_json_messages")

    if type(event_count) is not int or event_count != evidence["request_count"]:
        raise TrafficEvidenceError("invalid Envoy validated event count")

    if type(ignored_messages) is not int or ignored_messages < 0:
        raise TrafficEvidenceError("invalid ignored Envoy message count")

    return {
        "audit_status": "RECEIPT_INTEGRITY_VERIFIED",
        "run_id": run_id,
        "request_count": count,
        "workload_status": expected_status,
        "k6_capture_sha256": before["sha256"],
        "manifest_sha256": actual_manifest_digest,
        "docker_capture_sha256": evidence["docker_capture_sha256"],
        "request_ids_match": True,
        "receipt_integrity_verified": True,
        "envoy_raw_capture_reverified": False,
        "capture_completeness_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only collected evidence receipt audit"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--results-dir",
        default=str(
            Path(__file__).resolve().parents[1]
            / "testbed/results/final"
        ),
    )
    parser.add_argument("--allow-partial", action="store_true")

    args = parser.parse_args()

    try:
        result = audit_collected(
            args.run_id,
            args.results_dir,
            allow_partial=args.allow_partial,
        )
    except (TrafficEvidenceError, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"ok": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
