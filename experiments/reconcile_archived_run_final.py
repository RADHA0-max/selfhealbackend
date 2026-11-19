"""Fresh offline k6/Envoy reconciliation from preserved evidence bytes.

Does not attest capture completeness, runtime origin, or source-IP authenticity.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from experiments.docker_envoy_capture_final import normalize_docker_timestamps
from experiments.envoy_traffic_p15 import parse_envoy_jsonl
from experiments.request_reconciliation_final import reconcile_request_ids
from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_K6_BYTES = 8 * 1024 * 1024
MAX_K6_LINES = 100000
MAX_K6_LINE_BYTES = 65536
MAX_REQUESTS = 2000
RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, maximum):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    fd = os.open(str(path), flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise TrafficEvidenceError("evidence must be a regular file")
        if not 0 < before.st_size <= maximum:
            raise TrafficEvidenceError("invalid evidence file size")

        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(maximum + 1)

        after = os.fstat(fd)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(raw) != before.st_size
        ):
            raise TrafficEvidenceError("evidence changed during read")

        return raw
    finally:
        os.close(fd)


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TrafficEvidenceError("duplicate JSON key")
        result[key] = value
    return result


def reject_nonfinite(value):
    raise TrafficEvidenceError("nonfinite JSON constant")


def parse_k6_stream(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_K6_BYTES:
        raise TrafficEvidenceError("invalid k6 capture size")
    if not raw.endswith(b"\n"):
        raise TrafficEvidenceError("truncated k6 capture")

    ids = []
    lines = raw.splitlines()

    if not 1 <= len(lines) <= MAX_K6_LINES:
        raise TrafficEvidenceError("invalid k6 line count")

    for line in lines:
        if not line or len(line) > MAX_K6_LINE_BYTES:
            raise TrafficEvidenceError("invalid k6 line")

        try:
            record = json.loads(
                line.decode("utf-8"),
                object_pairs_hook=reject_duplicates,
                parse_constant=reject_nonfinite,
            )
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            raise TrafficEvidenceError("invalid k6 JSONL") from exc

        if type(record) is not dict:
            raise TrafficEvidenceError("invalid k6 record")

        if record.get("type") != "Point":
            continue

        if record.get("metric") != "nanoclaw_request_manifest":
            continue

        data = record.get("data")
        if type(data) is not dict or data.get("value") != 1:
            raise TrafficEvidenceError("invalid manifest metric")

        tags = data.get("tags")
        if type(tags) is not dict:
            raise TrafficEvidenceError("invalid manifest tags")

        if tags.get("workload") != "organic_60vu":
            raise TrafficEvidenceError("unexpected workload")

        request_id = tags.get("request_id")
        if (
            type(request_id) is not str
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id)
        ):
            raise TrafficEvidenceError("invalid k6 request ID")

        ids.append(request_id)

        if len(ids) > MAX_REQUESTS:
            raise TrafficEvidenceError("too many manifest requests")

    if not ids or len(ids) != len(set(ids)):
        raise TrafficEvidenceError("missing or duplicate k6 request IDs")

    return ids


def verify(run_id, results_dir):
    if type(run_id) is not str or not RUN_ID_RE.fullmatch(run_id):
        raise TrafficEvidenceError("invalid run ID")

    root = Path(results_dir)
    k6_path = root / (run_id + ".jsonl")
    envoy_path = root / (run_id + ".envoy-docker-stdout.log")
    receipt_path = root / (run_id + ".reserved/envoy-evidence.json")
    manifest_path = root / (run_id + ".raw-capture-verification.json")

    k6_raw = read_regular(k6_path, MAX_K6_BYTES)
    envoy_raw = read_regular(envoy_path, 1024 * 1024)
    receipt_raw = read_regular(receipt_path, 65536)
    manifest_raw = read_regular(manifest_path, 65536)

    receipt = json.loads(
        receipt_raw,
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_nonfinite,
    )
    manifest = json.loads(
        manifest_raw,
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_nonfinite,
    )

    if type(receipt) is not dict or type(manifest) is not dict:
        raise TrafficEvidenceError("invalid evidence metadata")

    if receipt.get("schema") != "nanoclaw.envoy-evidence.final.v1":
        raise TrafficEvidenceError("unexpected evidence receipt schema")

    if manifest.get("schema") != "nanoclaw.raw-capture-verification.v1":
        raise TrafficEvidenceError("unexpected archive manifest schema")

    if receipt.get("evidence_status") != "RECONCILED_UNATTESTED":
        raise TrafficEvidenceError("unexpected evidence status")

    if manifest.get("raw_capture_sha256_matches_receipt") is not True:
        raise TrafficEvidenceError("archive digest not verified")

    if manifest.get("receipt_integrity_verified") is not True:
        raise TrafficEvidenceError("receipt integrity not verified")

    if receipt.get("run_id") != run_id or manifest.get("run_id") != run_id:
        raise TrafficEvidenceError("run ID mismatch")

    if sha256(k6_raw) != receipt.get("k6_capture_sha256"):
        raise TrafficEvidenceError("k6 capture SHA-256 mismatch")

    if sha256(envoy_raw) != receipt.get("docker_capture_sha256"):
        raise TrafficEvidenceError("Envoy capture SHA-256 mismatch")

    if sha256(receipt_raw) != manifest.get("receipt_sha256"):
        raise TrafficEvidenceError("receipt SHA-256 mismatch")

    if sha256(envoy_raw) != manifest.get("archive_sha256"):
        raise TrafficEvidenceError("archive manifest SHA-256 mismatch")

    window = manifest.get("capture_window")
    if type(window) is not dict:
        raise TrafficEvidenceError("invalid capture window")

    since, until = window.get("since"), window.get("until")

    if since != receipt.get("since") or until != receipt.get("until"):
        raise TrafficEvidenceError("capture window mismatch")

    normalized = normalize_docker_timestamps(
        envoy_raw, since=since, until=until
    )

    events = parse_envoy_jsonl(normalized)
    k6_ids = parse_k6_stream(k6_raw)
    envoy_ids = [event["request_id"] for event in events]

    reconciliation = reconcile_request_ids(k6_ids, envoy_ids)

    if len(k6_ids) != receipt.get("request_count"):
        raise TrafficEvidenceError("k6 count differs from receipt")

    if len(events) != receipt.get("envoy_validated_event_count"):
        raise TrafficEvidenceError("Envoy count differs from receipt")

    if manifest.get("raw_stdout_records") != len(events):
        raise TrafficEvidenceError("archive event count differs")

    if receipt.get("request_ids_match") is not True:
        raise TrafficEvidenceError("original reconciliation not verified")

    if manifest.get("request_ids_match") is not True:
        raise TrafficEvidenceError("archive reconciliation not verified")

    if receipt.get("scheduled_iterations_complete") is not True:
        raise TrafficEvidenceError("scheduled iterations not complete")

    if receipt.get("missing_scheduled_iterations") != 0:
        raise TrafficEvidenceError("scheduled iterations missing")

    if receipt.get("scheduled_iterations") != len(k6_ids):
        raise TrafficEvidenceError("scheduled iteration count mismatch")

    if receipt.get("workload_status") != "COMPLETE":
        raise TrafficEvidenceError("workload not complete")

    return {
        "ok": True,
        "run_id": run_id,
        "k6_manifest_count": len(k6_ids),
        "envoy_event_count": len(events),
        "fresh_request_id_reconciliation": True,
        "request_ids_match": True,
        "k6_sha256_verified": True,
        "envoy_sha256_verified": True,
        "receipt_sha256_verified": True,
        "reconciliation_report": reconciliation,
        "capture_completeness_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "production_recovery_verified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--results-dir", default="testbed/results/final")
    args = parser.parse_args()

    try:
        result = verify(args.run_id, args.results_dir)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
