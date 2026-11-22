#!/usr/bin/env python3
"""Bounded P01 Envoy evidence collection; no provenance claims."""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from experiments.traffic_evidence_p15 import TrafficEvidenceError
from testbed.experiments.p01_evidence_adapter import (
    RUN_ID,
    normalize_envoy,
    parse_json,
    parse_k6_p01,
)

CONTAINER = "nanoclaw-p01-phase2-testbed-envoy-1"
MAX_SECONDS = 30
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_SELECTED_BYTES = 512_000
MAX_SELECTED_LINES = 2000


def select_records(log_bytes, run_id):
    if len(log_bytes) > MAX_LOG_BYTES:
        raise ValueError("Docker logs exceed size limit")

    selected = []
    selected_bytes = 0
    prefix = run_id + "-"

    for line in log_bytes.splitlines():
        if run_id.encode() not in line:
            continue

        if len(line) > 4096:
            raise ValueError("oversized candidate Envoy line")

        row = parse_json(line)

        if type(row) is not dict:
            raise ValueError("invalid Envoy log record")

        request_id = row.get("request_id")

        if type(request_id) is str and request_id.startswith(prefix):
            selected_bytes += len(line) + 1

            if selected_bytes > MAX_SELECTED_BYTES:
                raise ValueError("selected evidence exceeds size limit")

            selected.append(line)

            if len(selected) > MAX_SELECTED_LINES:
                raise ValueError("too many selected Envoy records")

    return b"\n".join(selected) + (b"\n" if selected else b"")


def read_logs(timeout=5):
    """Capture bounded Docker stdout and clean up the child process."""
    import selectors

    proc = None
    selector = selectors.DefaultSelector()

    try:
        proc = subprocess.Popen(
            ["docker", "logs", CONTAINER],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            shell=False,
        )

        if proc.stdout is None:
            raise RuntimeError("missing Docker stdout")

        selector.register(proc.stdout, selectors.EVENT_READ)

        captured = bytearray()
        deadline = time.monotonic() + min(5, timeout)

        while selector.get_map():
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                raise TimeoutError("Docker logs read timeout")

            for key, _ in selector.select(
                timeout=min(0.2, remaining)
            ):
                chunk = key.fileobj.read1(65536)

                if not chunk:
                    selector.unregister(key.fileobj)
                    continue

                if len(captured) + len(chunk) > MAX_LOG_BYTES:
                    raise ValueError("Docker logs exceed size limit")

                captured.extend(chunk)

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise TimeoutError("Docker logs read timeout")

        returncode = proc.wait(timeout=remaining)

        if returncode != 0:
            raise RuntimeError(
                f"isolated Envoy docker logs failed: {returncode}"
            )

        return bytes(captured)

    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("Docker logs read timeout") from exc

    finally:
        selector.close()

        if proc is not None:
            if proc.poll() is None:
                proc.kill()

            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

            if proc.stdout is not None:
                proc.stdout.close()


def atomic_write(path, data):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=".p01-envoy-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, destination)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def collect(run_id, k6_path, output_path, timeout=30):
    if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run ID")

    if type(timeout) is not int or not 0 < timeout <= MAX_SECONDS:
        raise ValueError("invalid timeout")

    expected = parse_k6_p01(Path(k6_path).read_bytes(), run_id)
    expected_ids = Counter(row["request_id"] for row in expected)

    if any(count != 1 for count in expected_ids.values()):
        raise ValueError("duplicate k6 request IDs")

    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise TimeoutError("Envoy evidence collection timed out")

        raw = select_records(
            read_logs(timeout=min(5.0, remaining)),
            run_id,
        )

        if time.monotonic() > deadline:
            raise TimeoutError("Envoy evidence collection timed out")

        # The strict Envoy parser requires at least two records.
        # A single record is incomplete evidence, so continue polling.
        if len(raw.splitlines()) >= 2:
            observed = normalize_envoy(raw, run_id)
            observed_ids = Counter(row["request_id"] for row in observed)

            if any(count != 1 for count in observed_ids.values()):
                raise ValueError("duplicate Envoy request IDs")

            if observed_ids.keys() - expected_ids.keys():
                raise ValueError("unexpected Envoy request IDs")

            if observed_ids == expected_ids:
                atomic_write(output_path, raw)
                return len(observed_ids)

        if time.monotonic() >= deadline:
            count = len(raw.splitlines())
            raise TimeoutError(
                f"Envoy evidence incomplete: {count}/{len(expected_ids)}"
            )

        time.sleep(min(0.5, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--k6", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    try:
        count = collect(
            args.run_id,
            args.k6,
            args.output,
            args.timeout,
        )
    except (
        ValueError,
        RuntimeError,
        TimeoutError,
        subprocess.SubprocessError,
        TrafficEvidenceError,
        OSError,
    ) as exc:
        print(f"P01 COLLECTION FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"P01 COLLECTION PASS: {count} matching Envoy records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
