#!/usr/bin/env python3
"""Offline P01 k6/Envoy evidence adapter. No runtime authenticity claims."""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.envoy_traffic_p15 import parse_envoy_jsonl
from experiments.traffic_evidence_p15 import TrafficEvidenceError
from testbed.experiments.measure_p01 import measure

MAX_K6_BYTES = 2 * 1024 * 1024
MAX_K6_LINES = 10000

WORKLOADS = {
    "ddos": "p01_ddos",
    "scraper": "p01_scraper",
    "nat": "p01_nat_control",
    "cache": "p01_cache",
    "p01_headless_botnet": "p01_headless_botnet",
    "p01_ambiguous": "p01_ambiguous",
    "p01_analytics": "p01_analytics",
}

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_json(line):
    return json.loads(
        line,
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("nonfinite JSON value")
        ),
    )


def classify(request_id, run_id):
    if type(request_id) is not str:
        raise ValueError("invalid request ID")

    prefix = run_id + "-"

    if not request_id.startswith(prefix):
        raise ValueError("request ID does not belong to run")

    suffix = request_id[len(prefix):]

    for marker, workload in WORKLOADS.items():
        if re.fullmatch(
            re.escape(marker) + r"-vu-[1-9][0-9]*-iter-[0-9]+",
            suffix,
        ):
            return workload

    raise ValueError("unknown P01 request ID pattern")


def parse_k6_p01(raw, run_id):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_K6_BYTES:
        raise ValueError("invalid k6 evidence size")

    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("invalid k6 encoding") from exc

    if not 1 <= len(lines) <= MAX_K6_LINES:
        raise ValueError("invalid k6 evidence line count")

    events = []

    for line in lines:
        if not line or len(line.encode("utf-8")) > 4096:
            raise ValueError("invalid k6 line")

        record = parse_json(line)

        if type(record) is not dict:
            raise ValueError("invalid k6 record")

        if record.get("type") != "Point":
            continue

        if record.get("metric") != "nanoclaw_request_manifest":
            continue

        data = record.get("data")
        if type(data) is not dict:
            raise ValueError("invalid k6 metric data")

        tags = data.get("tags")
        if type(tags) is not dict or data.get("value") != 1:
            raise ValueError("invalid k6 manifest point")

        request_id = tags.get("request_id")
        workload = classify(request_id, run_id)

        if tags.get("workload") != workload:
            raise ValueError("k6 workload tag mismatch")

        events.append({
            "run_id": run_id,
            "request_id": request_id,
            "workload": workload,
        })

    if not events:
        raise ValueError("no P01 manifest events")

    return events


def normalize_envoy(raw, run_id):
    # Validate cache query strings before passing evidence to the
    # existing strict Envoy parser. Do not modify shared parser rules.
    if type(raw) is not bytes:
        raise ValueError("invalid Envoy evidence")

    normalized = []

    for line in raw.splitlines(keepends=True):
        row = parse_json(line)
        if type(row) is not dict:
            raise ValueError("invalid Envoy record")

        path = row.get("path")

        if type(path) is str and "?" in path:
            request_id = row.get("request_id")
            if classify(request_id, run_id) != "p01_cache":
                raise ValueError("query string outside cache workload")

            match = re.fullmatch(
                r"/api/data\?cache_key=([A-Za-z0-9_-]{1,80})",
                path,
            )
            if not match:
                raise ValueError("invalid cache query string")

            key = match.group(1)
            if not key.startswith(run_id + "-"):
                raise ValueError("cache key does not belong to run")

            row["path"] = "/api/data"
            line = (json.dumps(row, separators=(",", ":")) + "\n").encode()

        normalized.append(line)

    # Preserve strict schema, timestamps, IPs, methods, IDs and limits.
    rows = parse_envoy_jsonl(b"".join(normalized))

    return [
        {
            "run_id": run_id,
            "request_id": row["request_id"],
            "workload": classify(row["request_id"], run_id),
        }
        for row in rows
    ]


def reconcile(k6_raw, envoy_raw, run_id, expected_workload=None):
    if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run ID")

    if expected_workload is not None and expected_workload not in WORKLOADS.values():
        raise ValueError("invalid expected workload")

    expected = parse_k6_p01(k6_raw, run_id)
    observed = normalize_envoy(envoy_raw, run_id)

    if expected_workload is not None:
        for event in expected + observed:
            if event["workload"] != expected_workload:
                raise ValueError("unexpected workload in evidence")

    result = measure(expected, observed)

    result.update({
        "run_id": run_id,
        "k6_capture_complete_verified": False,
        "envoy_capture_complete_verified": False,
        "runtime_origin_verified": False,
        "source_ip_verified": False,
        "network_isolation_verified": False,
    })

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--workload",
        required=True,
        choices=sorted(set(WORKLOADS.values())),
    )
    parser.add_argument("--k6", required=True)
    parser.add_argument("--envoy", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        result = reconcile(
            Path(args.k6).read_bytes(),
            Path(args.envoy).read_bytes(),
            args.run_id,
            expected_workload=args.workload,
        )
    except (ValueError, TrafficEvidenceError, OSError) as exc:
        print("P01 EVIDENCE FAIL:", exc, file=sys.stderr)
        return 1

    report = json.dumps(result, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(report + "\n", encoding="utf-8")

    print(report)

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
