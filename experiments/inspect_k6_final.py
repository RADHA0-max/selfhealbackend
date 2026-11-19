"""Inspect a completed local k6 JSON output without starting traffic."""

import argparse
import json

from experiments.k6_stream_final import extract_k6_manifest
from experiments.traffic_evidence_p15 import TrafficEvidenceError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", help="completed k6 --out json file")
    args = parser.parse_args()

    try:
        result = extract_k6_manifest(args.capture)
    except TrafficEvidenceError as exc:
        parser.exit(2, f"INVALID CAPTURE: {exc}\\n")

    report = {
        "request_count": result["request_count"],
        "input_bytes": result["input_bytes"],
        "capture_complete_verified": False,
        "runtime_origin_verified": False,
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
