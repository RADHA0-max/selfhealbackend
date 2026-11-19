"""Explicit, bounded k6 experiment launcher.

No Docker operation occurs without --execute.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from experiments.k6_stream_final import extract_k6_manifest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "testbed/results/final"
COMPOSE = [
    "docker", "compose",
    "-f", str(ROOT / "testbed/compose.yaml"),
    "-f", str(ROOT / "testbed/compose.k6-final.yaml"),
    "--profile", "traffic",
]
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


def prepare(run_id):
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("Invalid run ID")

    if not RESULTS.is_dir():
        raise ValueError("Results directory does not exist")

    capture = RESULTS / f"{run_id}.jsonl"

    # Refuse existing captures, including symlinks.
    reservation = RESULTS / f"{run_id}.reserved"
    if capture.is_symlink() or capture.exists():
        raise FileExistsError(f"Capture already exists: {capture}")
    if reservation.is_symlink() or reservation.exists():
        raise FileExistsError(f"Run ID already reserved: {reservation}")

    return capture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly start the isolated k6 workload",
    )
    args = parser.parse_args()

    try:
        capture = prepare(args.run_id)
    except (ValueError, FileExistsError) as exc:
        parser.exit(2, f"PRECHECK FAILED: {exc}\n")

    if not args.execute:
        print(json.dumps({
            "status": "READY_NOT_EXECUTED",
            "run_id": args.run_id,
            "capture": str(capture),
            "traffic_started": False,
        }, sort_keys=True))
        return

    # Atomically reserve this run ID without pre-creating the capture file.
    # The container must create the JSONL output itself.
    reservation = RESULTS / f"{args.run_id}.reserved"
    try:
        reservation.mkdir(mode=0o700)
    except FileExistsError:
        parser.exit(2, "RUN ID ALREADY RESERVED\n")

    env = os.environ.copy()
    env["NANOCLAW_RUN_ID"] = args.run_id

    receipt = reservation / "status.json"

    def record(status, **details):
        payload = {
            "run_id": args.run_id,
            "status": status,
            "capture": str(capture),
            "capture_complete_verified": False,
            "runtime_origin_verified": False,
            "source_ip_verified": False,
            "envoy_reconciled": False,
            **details,
        }
        temp = reservation / "status.tmp"
        temp.write_text(json.dumps(payload, sort_keys=True) + "\n")
        temp.replace(receipt)

    record("RESERVED")

    # Verify existing dependencies without starting containers.
    try:
        check = subprocess.run(
            COMPOSE + ["ps", "--status", "running", "--services"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        record("PREFLIGHT_FAILED", error=str(exc))
        parser.exit(125, f"DEPENDENCY PREFLIGHT FAILED: {exc}\n")

    if check.returncode:
        record("PREFLIGHT_FAILED", exit_code=check.returncode)
        parser.exit(125, "DEPENDENCY PREFLIGHT FAILED\n")

    running = set(check.stdout.splitlines())
    required = {"testbed-envoy", "testbed-app"}

    if not required.issubset(running):
        missing = sorted(required - running)
        record("PREFLIGHT_FAILED", missing=missing)
        parser.exit(
            125,
            f"DEPENDENCIES NOT RUNNING: {', '.join(missing)}\n",
        )

    # The launcher never starts the application or Envoy dependencies.
    # Docker execution remains explicitly gated by --execute.
    try:
        result = subprocess.run(
            COMPOSE + [
                "run", "--rm", "--no-deps",
                "--name", f"nanoclaw-k6-{args.run_id}",
                "testbed-k6",
            ],
            cwd=ROOT,
            env=env,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        record("TIMED_OUT")
        try:
            cleanup = subprocess.run(
                ["docker", "rm", "-f", f"nanoclaw-k6-{args.run_id}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
            if cleanup.returncode:
                record("TIMED_OUT_CLEANUP_FAILED",
                       cleanup_exit_code=cleanup.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            record("TIMED_OUT_CLEANUP_FAILED", error=str(exc))
        parser.exit(124, "K6 EXECUTION TIMED OUT\n")
    except OSError as exc:
        record("LAUNCH_FAILED", error=str(exc))
        parser.exit(125, f"K6 LAUNCH FAILED: {exc}\n")

    if result.returncode:
        record("K6_FAILED", exit_code=result.returncode)
        parser.exit(
            result.returncode,
            f"K6 FAILED: exit code {result.returncode}\n",
        )

    try:
        report = extract_k6_manifest(str(capture))
    except Exception as exc:
        record("CAPTURE_INVALID", error=str(exc))
        parser.exit(2, f"CAPTURE VALIDATION FAILED: {exc}\n")

    record(
        "CAPTURE_PARSED",
        request_count=report["request_count"],
    )

    print(json.dumps({
        "status": "CAPTURE_PARSED",
        "run_id": args.run_id,
        "request_count": report["request_count"],
        "capture_complete_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "envoy_reconciled": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
