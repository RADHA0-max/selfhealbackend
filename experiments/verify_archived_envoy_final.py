"""Offline verification of preserved Docker Envoy stdout evidence."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from experiments.docker_envoy_capture_final import normalize_docker_timestamps
from experiments.envoy_traffic_p15 import parse_envoy_jsonl


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(run_id, results_dir):
    root = Path(results_dir)
    archive = root / (run_id + ".envoy-docker-stdout.log")
    manifest = root / (run_id + ".raw-capture-verification.json")
    receipt = root / (run_id + ".reserved/envoy-evidence.json")

    for path in (archive, manifest, receipt):
        if not path.is_file() or path.is_symlink():
            raise ValueError("missing or unsafe evidence file: " + path.name)

    metadata = json.loads(manifest.read_text())
    evidence = json.loads(receipt.read_text())
    raw = archive.read_bytes()

    if metadata.get("run_id") != run_id:
        raise ValueError("manifest run ID mismatch")

    if evidence.get("run_id") != run_id:
        raise ValueError("receipt run ID mismatch")

    expected = evidence.get("docker_capture_sha256")

    if not isinstance(expected, str) or digest(raw) != expected:
        raise ValueError("archived Docker capture SHA-256 mismatch")

    if metadata.get("archive_sha256") != expected:
        raise ValueError("manifest capture SHA-256 mismatch")

    if metadata.get("receipt_sha256") != digest(receipt.read_bytes()):
        raise ValueError("receipt SHA-256 mismatch")

    window = metadata.get("capture_window")

    if not isinstance(window, dict):
        raise ValueError("missing capture window")

    if (
        window.get("since") != evidence.get("since")
        or window.get("until") != evidence.get("until")
    ):
        raise ValueError("capture window mismatch")

    normalized = normalize_docker_timestamps(
        raw,
        since=window["since"],
        until=window["until"],
    )

    events = parse_envoy_jsonl(normalized)
    ids = [event["request_id"] for event in events]

    if not all(ids):
        raise ValueError("empty request ID")

    if len(ids) != len(set(ids)):
        raise ValueError("duplicate request ID")

    if len(events) != evidence.get("envoy_validated_event_count"):
        raise ValueError("Envoy event count mismatch")

    if len(events) != evidence.get("request_count"):
        raise ValueError("request count mismatch")

    if metadata.get("raw_stdout_records") != len(events):
        raise ValueError("manifest record count mismatch")

    if evidence.get("request_ids_match") is not True:
        raise ValueError("original reconciliation not verified")

    return {
        "ok": True,
        "run_id": run_id,
        "archive_sha256_verified": True,
        "receipt_sha256_verified": True,
        "docker_independent": True,
        "validated_events": len(events),
        "unique_envoy_request_ids": len(set(ids)),
        "original_reconciliation_receipt_verified": True,
        "fresh_k6_id_reconciliation_performed": False,
        "capture_completeness_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--results-dir",
        default="testbed/results/final",
    )
    args = parser.parse_args()

    try:
        result = verify(args.run_id, args.results_dir)
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "error": str(exc),
        }))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
