"""Bounded, read-only comparison of synthetic traffic controls.

Synthetic IP labels and sessions are not authenticated identities.
Request-rate differences are not attack classifications.
"""

from __future__ import annotations

import math
import re

from experiments.traffic_evidence_p15 import (
    TrafficEvidenceError,
    summarize_traffic,
)

MAX_CANDIDATES = 10
MAX_RATE_RATIO = 1_000_000
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _single_scenario(summary):
    counts = summary["scenario_counts"]

    if len(counts) != 1:
        raise TrafficEvidenceError("mixed scenarios are not comparable")

    return next(iter(counts))


def evaluate_controls(organic, candidates):
    """Compare synthetic traces; candidate names are not classifications."""
    if type(candidates) is not dict or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise TrafficEvidenceError("invalid candidate scenarios")

    baseline = summarize_traffic(organic)

    if _single_scenario(baseline) != "organic":
        raise TrafficEvidenceError("baseline must be organic")

    baseline_rate = baseline["requests_per_second"]

    if not math.isfinite(baseline_rate) or baseline_rate <= 0:
        raise TrafficEvidenceError("invalid baseline rate")

    results = {}

    for name, events in candidates.items():
        if type(name) is not str or not NAME.fullmatch(name):
            raise TrafficEvidenceError("invalid scenario name")

        measured = summarize_traffic(events)
        scenario = _single_scenario(measured)

        rate = measured["requests_per_second"]
        ratio = rate / baseline_rate

        if not math.isfinite(ratio) or ratio > MAX_RATE_RATIO:
            raise TrafficEvidenceError("invalid rate ratio")

        results[name] = {
            "scenario": scenario,
            "request_count": measured["request_count"],
            "requests_per_second": rate,
            "rate_ratio": round(ratio, 3),
            "unique_sessions": measured["unique_sessions"],
            "synthetic_ip_labels": measured["synthetic_ip_labels"],
            "http_5xx_count": measured["http_5xx_count"],
            "attack_classification": "not_evaluated",
            "source_ip_separation_verified": False,
        }

    return {
        "report_version": 1,
        "evidence_source": "synthetic_traffic_controls",
        "baseline": baseline,
        "candidates": results,
        "detector_classification_verified": False,
        "production_traffic_verified": False,
        "mitigation_executed": False,
    }
