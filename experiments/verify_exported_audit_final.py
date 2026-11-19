"""Verify an exported offline audit against freshly rechecked evidence."""

import argparse
import json
import sys
from pathlib import Path

from experiments.export_archived_audit_final import build_report, serialize_report
from experiments.reconcile_archived_run_final import (
    RUN_ID_RE,
    read_regular,
)


def verify_export(run_id, results_dir, audit_dir):
    if type(run_id) is not str or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid run ID")

    path = Path(audit_dir) / (run_id + ".offline-audit.json")

    raw = read_regular(path, 1024 * 1024)

    exported = json.loads(raw)

    if type(exported) is not dict:
        raise ValueError("invalid audit report")

    expected = build_report(run_id, results_dir)

    if exported != expected:
        raise ValueError("exported audit differs from verified evidence")

    if raw != serialize_report(expected):
        raise ValueError("noncanonical audit report bytes")

    return {
        "ok": True,
        "run_id": run_id,
        "report_verified": True,
        "fresh_reconciliation_performed": True,
        "request_ids_match": True,
        "audit_status": expected["audit_status"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--results-dir",
        default="testbed/results/final",
    )
    parser.add_argument(
        "--audit-dir",
        default="testbed/results/final/audits",
    )
    args = parser.parse_args()

    try:
        result = verify_export(
            args.run_id,
            args.results_dir,
            args.audit_dir,
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
