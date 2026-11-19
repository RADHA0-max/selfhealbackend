"""Export a reproducible offline audit report without modifying evidence."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from experiments.reconcile_archived_run_final import (
    RUN_ID_RE,
    read_regular,
    sha256,
    verify,
)


def build_report(run_id, results_dir):
    audit = verify(run_id, results_dir)
    root = Path(results_dir)

    evidence_files = {
        "k6_capture": root / (run_id + ".jsonl"),
        "envoy_archive": root / (
            run_id + ".envoy-docker-stdout.log"
        ),
        "envoy_receipt": root / (
            run_id + ".reserved/envoy-evidence.json"
        ),
        "archive_manifest": root / (
            run_id + ".raw-capture-verification.json"
        ),
    }

    evidence_hashes = {}

    for name, path in evidence_files.items():
        raw = read_regular(path, 8 * 1024 * 1024)
        evidence_hashes[name] = {
            "sha256": sha256(raw),
            "bytes": len(raw),
        }

    return {
        "schema": "nanoclaw.archived-offline-audit.v1",
        "run_id": run_id,
        "audit_status": "OFFLINE_RECONCILED_UNATTESTED",
        "audit": audit,
        "evidence_files": evidence_hashes,
        "limitations": {
            "capture_completeness_verified": False,
            "runtime_origin_verified": False,
            "source_ip_verified": False,
            "production_recovery_verified": False,
            "independent_external_attestation": False,
        },
    }



def serialize_report(report):
    """Produce deterministic UTF-8 JSON bytes for an audit report."""
    return (
        json.dumps(
            report,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

def export_report(run_id, results_dir, output_dir):
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid run ID")

    report = build_report(run_id, results_dir)

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    output = destination / (run_id + ".offline-audit.json")

    payload = serialize_report(report)

    # Write a complete temporary file before publishing the report.
    # Hard-link publication is atomic and fails if the target exists.
    temp_path = None

    try:
        fd, temp_name = tempfile.mkstemp(
            prefix="." + run_id + ".audit-",
            suffix=".tmp",
            dir=str(destination),
        )
        temp_path = Path(temp_name)

        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        os.link(str(temp_path), str(output), follow_symlinks=False)

        # Persist the directory entry when supported.
        directory_fd = os.open(
            str(destination),
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    return {
        "ok": True,
        "report_path": str(output),
        "report_sha256": hashlib.sha256(payload).hexdigest(),
        "audit_status": report["audit_status"],
        "request_ids_match": report["audit"]["request_ids_match"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--results-dir",
        default="testbed/results/final",
    )
    parser.add_argument(
        "--output-dir",
        default="testbed/results/final/audits",
    )
    args = parser.parse_args()

    try:
        result = export_report(
            args.run_id,
            args.results_dir,
            args.output_dir,
        )
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
