"""Read-only audit of a reserved k6 run and captured Envoy evidence."""

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

from experiments.verify_traffic_final import verify
from experiments.traffic_evidence_p15 import TrafficEvidenceError

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
MAX_RECEIPT_BYTES = 16384


def read_receipt(path):
    flags = os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    fd = os.open(str(path), flags)

    try:
        before = os.fstat(fd)

        if not stat.S_ISREG(before.st_mode):
            raise TrafficEvidenceError("receipt is not a regular file")

        if not 0 < before.st_size <= MAX_RECEIPT_BYTES:
            raise TrafficEvidenceError("invalid receipt size")

        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(MAX_RECEIPT_BYTES + 1)

        after = os.fstat(fd)

        if (
            len(raw) != before.st_size
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ino != after.st_ino
        ):
            raise TrafficEvidenceError("receipt changed during read")

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise TrafficEvidenceError("duplicate receipt key")
                result[key] = value
            return result

        def reject_constant(value):
            raise TrafficEvidenceError("invalid receipt number")

        try:
            result = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=unique_pairs,
                parse_constant=reject_constant,
            )
        except (UnicodeError, ValueError) as exc:
            raise TrafficEvidenceError("invalid receipt JSON") from exc

        if not isinstance(result, dict):
            raise TrafficEvidenceError("invalid receipt object")

        return result

    finally:
        os.close(fd)


def audit(run_id, envoy_path, results_dir, *, allow_partial=False):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise TrafficEvidenceError("invalid run ID")

    root = Path(results_dir)

    if root.is_symlink() or not root.is_dir():
        raise TrafficEvidenceError("invalid results directory")

    reservation = root / f"{run_id}.reserved"

    if reservation.is_symlink() or not reservation.is_dir():
        raise TrafficEvidenceError("missing run reservation")

    receipt = read_receipt(reservation / "status.json")

    if receipt.get("run_id") != run_id:
        raise TrafficEvidenceError("receipt run ID mismatch")

    if receipt.get("status") != "CAPTURE_PARSED":
        raise TrafficEvidenceError("runner did not complete capture parsing")

    capture = root / f"{run_id}.jsonl"

    if receipt.get("capture") != str(capture):
        raise TrafficEvidenceError("receipt capture path mismatch")

    result = verify(
        str(capture),
        str(envoy_path),
        run_id,
        require_complete=not allow_partial,
    )

    if receipt.get("request_count") != result["k6_request_count"]:
        raise TrafficEvidenceError("receipt request count mismatch")

    if result.get("request_ids_match") is not True:
        raise TrafficEvidenceError(
            "k6 and Envoy request IDs do not reconcile"
        )

    return {
        "audit_status": "EVIDENCE_RECONCILED",
        "run_id": run_id,
        "runner_receipt_status": receipt["status"],
        "workload_status": result["workload_status"],
        "request_count": result["k6_request_count"],
        "request_ids_match": result["request_ids_match"],
        "scheduled_iterations_complete": result[
            "scheduled_iterations_complete"
        ],
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "capture_completeness_verified": False,
        "production_recovery_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only k6 runner/Envoy evidence audit"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--envoy", required=True)
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
        result = audit(
            args.run_id,
            args.envoy,
            args.results_dir,
            allow_partial=args.allow_partial,
        )
    except (TrafficEvidenceError, OSError, ValueError) as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"ok": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
