"""Read-only, fail-closed k6/Envoy request evidence verifier."""

import argparse
import json
import re
import sys

from experiments.envoy_stream_final import reconcile_envoy_stream
from experiments.k6_stream_final import extract_k6_manifest
from experiments.traffic_evidence_p15 import TrafficEvidenceError

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


def verify(k6_path, envoy_path, run_id, require_complete=False):
    if not RUN_ID.fullmatch(run_id):
        raise TrafficEvidenceError("invalid run ID")

    manifest = extract_k6_manifest(k6_path)

    pattern = re.compile(
        rf"{re.escape(run_id)}-organic-vu-"
        r"([1-9][0-9]*)-iter-(0|[1-9][0-9]*)\Z"
    )

    pairs = set()

    for request_id in manifest["request_ids"]:
        match = pattern.fullmatch(request_id)

        if match is None:
            raise TrafficEvidenceError(
                "invalid workload request ID"
            )

        vu = int(match.group(1))
        iteration = int(match.group(2))

        if not 1 <= vu <= 60 or not 0 <= iteration < 20:
            raise TrafficEvidenceError(
                "request outside bounded workload"
            )

        pair = (vu, iteration)

        if pair in pairs:
            raise TrafficEvidenceError(
                "duplicate VU/iteration pair"
            )

        pairs.add(pair)

    scheduled = 60 * 20
    completed = len(pairs)

    reconciliation = reconcile_envoy_stream(
        envoy_path, manifest["request_ids"]
    )

    result = {
        "k6_request_count": manifest["request_count"],
        "request_reconciliation": reconciliation,
        "k6_capture_complete_verified": False,
        "envoy_capture_complete_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }

    result["run_id"] = run_id
    result["scheduled_iterations"] = scheduled
    result["observed_manifest_requests"] = completed
    result["missing_scheduled_iterations"] = scheduled - completed
    result["scheduled_iterations_complete"] = completed == scheduled
    result["workload_status"] = (
        "COMPLETE" if completed == scheduled else "PARTIAL"
    )
    result["request_ids_match"] = result[
        "request_reconciliation"
    ]["request_ids_match"]

    result["capture_completeness_verified"] = False
    result["runtime_origin_verified"] = False
    result["source_ip_verified"] = False
    result["production_recovery_verified"] = False

    if require_complete and completed != scheduled:
        raise TrafficEvidenceError(
            f"incomplete workload: {completed}/{scheduled} requests"
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Verify bounded k6/Envoy evidence offline"
    )
    parser.add_argument("--k6", required=True)
    parser.add_argument("--envoy", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow partial workload evidence (not full-run success)",
    )

    args = parser.parse_args()

    try:
        result = verify(
            args.k6,
            args.envoy,
            args.run_id,
            require_complete=not args.allow_partial,
        )
    except (TrafficEvidenceError, OSError, ValueError) as exc:
        print(
            json.dumps({
                "ok": False,
                "error": str(exc),
            }),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({
        "ok": True,
        "result": result,
    }, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
