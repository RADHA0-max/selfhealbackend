"""Bounded offline Docker Envoy-log capture.

No shell, no automatic container startup, no traffic generation.
Docker log origin and completeness are not independently attested.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
import os
import re
import selectors
import subprocess
import time

from experiments.envoy_stdout_final import (
    MAX_CAPTURE_BYTES,
    extract_envoy_stdout,
)
from experiments.traffic_evidence_p15 import TrafficEvidenceError
from experiments.envoy_reconciliation_final import reconcile_envoy_jsonl

CAPTURE_TIMEOUT_SECONDS = 15
DOCKER_TIMESTAMP = re.compile(
    rb"^\d{4}-\d{2}-\d{2}T"
    rb"\d{2}:\d{2}:\d{2}\.\d{1,9}Z "
)
CONTAINER_NAME = re.compile(r"nanoclaw-[A-Za-z0-9_.-]{1,90}\Z")


def normalize_docker_timestamps(raw, *, since=None, until=None):
    """Validate Docker timestamps and strip prefixes.

    If a window is supplied, every captured line must fall within it.
    """
    if (since is None) != (until is None):
        raise TrafficEvidenceError("incomplete experiment window")
    window = None
    if since is not None:
        _validate_window(since, until)
        window = (
            datetime.fromisoformat(since[:-1] + "+00:00"),
            datetime.fromisoformat(until[:-1] + "+00:00"),
        )
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CAPTURE_BYTES:
        raise TrafficEvidenceError("invalid Docker capture size")
    if not raw.endswith(b"\n"):
        raise TrafficEvidenceError("unterminated Docker capture")

    normalized = []
    for line in raw.splitlines():
        match = DOCKER_TIMESTAMP.match(line)
        if match is None:
            raise TrafficEvidenceError("missing Docker timestamp prefix")
        timestamp = match.group()[:-1].decode("ascii")
        try:
            # Docker supports nanoseconds; Python datetime supports microseconds.
            # Validate the full timestamp before converting its fractional part.
            date_part, fractional = timestamp[:-1].split(".", 1)
            if not 1 <= len(fractional) <= 9 or not fractional.isdigit():
                raise ValueError("invalid Docker timestamp precision")
            instant = datetime.fromisoformat(
                date_part + "." + fractional[:6].ljust(6, "0") + "+00:00"
            )
        except ValueError as exc:
            raise TrafficEvidenceError("invalid Docker timestamp") from exc
        if window is not None and not window[0] <= instant <= window[1]:
            raise TrafficEvidenceError("Docker record outside experiment window")
        normalized.append(line[match.end():])

    return b"\n".join(normalized) + b"\n"


def _bounded_read_process(proc):
    """Read bounded Docker streams; permit only Envoy diagnostics on stderr."""
    import selectors
    import time

    selector = selectors.DefaultSelector()
    streams = {}

    for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        if pipe is None:
            raise TrafficEvidenceError("missing Docker stream")
        selector.register(pipe, selectors.EVENT_READ, name)
        streams[name] = bytearray()

    deadline = time.monotonic() + CAPTURE_TIMEOUT_SECONDS

    try:
        while selector.get_map():
            if time.monotonic() > deadline:
                raise TrafficEvidenceError("Docker log read timeout")

            for key, _ in selector.select(timeout=0.2):
                chunk = key.fileobj.read1(65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue

                name = key.data
                streams[name].extend(chunk)

                if len(streams[name]) > 1024 * 1024:
                    raise TrafficEvidenceError("Docker stream exceeds size limit")

        if proc.wait(timeout=2) != 0:
            raise TrafficEvidenceError("Docker logs command failed")

        stderr = bytes(streams["stderr"])

        if stderr:
            for line in stderr.splitlines():
                if not line:
                    raise TrafficEvidenceError("empty Docker stderr line")

                try:
                    text = line.decode("utf-8", "strict")
                except UnicodeDecodeError as exc:
                    raise TrafficEvidenceError("invalid Docker stderr encoding") from exc

                # Envoy diagnostic lines start with an ISO timestamp followed
                # by Envoy's own bracketed timestamp and severity.
                import re
                if not re.match(
                    r"^\d{4}-\d{2}-\d{2}T"
                    r"\d{2}:\d{2}:\d{2}\.\d+Z "
                    r"\[\d{4}-\d{2}-\d{2} "
                    r"\d{2}:\d{2}:\d{2}\.\d+\]"
                    r"\[\d+\]\[(?:trace|debug|info|warning|error|critical)\]",
                    text,
                ):
                    raise TrafficEvidenceError("unexpected Docker stderr")

        return bytes(streams["stdout"])

    finally:
        selector.close()

def _validate_window(since, until):
    """Require a bounded UTC experiment window of at most ten minutes."""
    if type(since) is not str or type(until) is not str:
        raise TrafficEvidenceError("experiment timestamps must be strings")

    def parse(value):
        if not value.endswith("Z"):
            raise TrafficEvidenceError("experiment timestamps must be UTC")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise TrafficEvidenceError("invalid experiment timestamp") from exc
        if parsed.utcoffset().total_seconds() != 0:
            raise TrafficEvidenceError("non-UTC experiment timestamp")
        return parsed

    start = parse(since)
    end = parse(until)

    if not 0 < (end - start).total_seconds() <= 600:
        raise TrafficEvidenceError("invalid experiment window")

    return since, until


def capture_envoy_logs(
    container_name, *, since, until, expected_request_ids=None
):
    """Capture one bounded Docker log window and validate Envoy records."""
    if type(container_name) is not str or not CONTAINER_NAME.fullmatch(
        container_name
    ):
        raise TrafficEvidenceError("invalid container name")

    since, until = _validate_window(since, until)

    proc = None
    try:
        proc = subprocess.Popen(
            [
                "docker", "logs", "--timestamps",
                "--since", since,
                "--until", until,
                container_name,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            shell=False,
        )

        raw = _bounded_read_process(proc)
        normalized = normalize_docker_timestamps(
            raw, since=since, until=until
        )
        report = extract_envoy_stdout(
            normalized,
            capture_complete=True,
        )

        if expected_request_ids is not None:
            report["request_reconciliation"] = reconcile_envoy_jsonl(
                report["validated_evidence_jsonl"],
                expected_request_ids,
            )

        report.pop("validated_evidence_jsonl", None)
        report["docker_capture_sha256"] = hashlib.sha256(raw).hexdigest()
        report["docker_container_name"] = container_name
        report["experiment_since"] = since
        report["experiment_until"] = until
        report["experiment_request_count_reconciled"] = False
        report["capture_complete_asserted_by_caller"] = False
        report["docker_command_completed"] = True
        report["runtime_origin_verified"] = False

        return report

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise TrafficEvidenceError("Docker capture failed") from exc
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
