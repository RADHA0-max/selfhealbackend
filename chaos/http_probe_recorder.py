"""Bounded HTTP probe recorder for explicitly authorized local testbeds."""

from __future__ import annotations

import ipaddress
import math
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from chaos.recovery_timeline import evaluate_timeline


class ProbeError(ValueError):
    """Unsafe probe configuration or failed observation."""


MAX_PROBES = 10
MAX_INTERVAL_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 5.0


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeError("HTTP redirects are prohibited")


def validate_probe_url(url: str) -> str:
    """Allow HTTP requests only to explicit loopback IPv4 addresses."""

    if not isinstance(url, str) or len(url) > 256:
        raise ProbeError("invalid probe URL")

    parsed = urlsplit(url)

    if parsed.scheme != "http":
        raise ProbeError("only HTTP is supported")

    if parsed.username is not None or parsed.password is not None:
        raise ProbeError("credentials in URLs are prohibited")

    if parsed.fragment or parsed.query:
        raise ProbeError("query strings and fragments are prohibited")

    try:
        address = ipaddress.ip_address(parsed.hostname)
        port = parsed.port
    except (ValueError, TypeError) as exc:
        raise ProbeError("invalid probe address") from exc

    if address.version != 4 or not address.is_loopback:
        raise ProbeError("only IPv4 loopback targets are permitted")

    if port is None or not 1 <= port <= 65535:
        raise ProbeError("explicit port required")

    if parsed.path not in ("/health", "/ready"):
        raise ProbeError("only health endpoints are permitted")

    return url


def record_http_probes(
    url: str,
    *,
    count: int = 5,
    interval_seconds: float = 1.0,
    timeout_seconds: float = 2.0,
    target: str = "api",
    clock: Any = None,
    sleep: Any = None,
    opener: Any = None,
) -> list[dict[str, Any]]:
    """Collect bounded observations; no retries and no automatic mitigation."""

    validate_probe_url(url)

    if type(count) is not int or not 2 <= count <= MAX_PROBES:
        raise ProbeError("count must be 2..10")

    if type(interval_seconds) not in (int, float) or not (
        math.isfinite(interval_seconds)
        and 0.1 <= interval_seconds <= MAX_INTERVAL_SECONDS
    ):
        raise ProbeError("invalid probe interval")

    if type(timeout_seconds) not in (int, float) or not (
        math.isfinite(timeout_seconds)
        and 0.1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS
    ):
        raise ProbeError("invalid timeout")

    if type(target) is not str or target not in ("api", "auth", "worker", "database"):
        raise ProbeError("unsupported target")

    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    opener = opener or build_opener(ProxyHandler({}), NoRedirect())

    events = []
    origin = clock()

    for index in range(count):
        if index:
            sleep(interval_seconds)

        started = clock()

        try:
            request = Request(url, method="GET")
            with opener.open(request, timeout=timeout_seconds) as response:
                status = response.status

        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise ProbeError("HTTP redirect prohibited") from exc
            status = exc.code

        except URLError as exc:
            raise ProbeError("probe connection failed") from exc

        finished = clock()
        timestamp_ms = int((started - origin) * 1000)
        if events and timestamp_ms <= events[-1]["time_ms"]:
            raise ProbeError(
                "probe timestamps lack sufficient measurement resolution"
            )

        events.append({
            "time_ms": timestamp_ms,
            "target": target,
            "status": status,
            "latency_ms": int((finished - started) * 1000),
        })

    return events


def evaluate_http_probes(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate collected probe observations without claiming causality."""
    return evaluate_timeline(events)
