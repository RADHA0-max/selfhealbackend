import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "p01_evidence_adapter.py"
)

spec = importlib.util.spec_from_file_location("p01_adapter", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def k6_point(request_id, workload):
    return {
        "type": "Point",
        "metric": "nanoclaw_request_manifest",
        "data": {
            "value": 1,
            "tags": {
                "request_id": request_id,
                "workload": workload,
            },
        },
    }


def envoy_point(request_id, offset):
    timestamp = (
        datetime(2026, 1, 1, tzinfo=timezone.utc)
        + timedelta(milliseconds=offset)
    ).isoformat()

    return {
        "timestamp": timestamp,
        "client_ip": "192.0.2.10",
        "method": "GET",
        "path": "/api/data",
        "status": 200,
        "duration_ms": 10,
        "user_agent": "NanoClaw-Test/1.0",
        "request_id": request_id,
    }


def jsonl(rows):
    return (
        "\n".join(json.dumps(row) for row in rows) + "\n"
    ).encode()


class P01AdapterTests(unittest.TestCase):

    def test_ddos_reconciles(self):
        ids = [
            "runA-ddos-vu-1-iter-0",
            "runA-ddos-vu-2-iter-0",
        ]

        k6 = jsonl([k6_point(x, "p01_ddos") for x in ids])
        envoy = jsonl([
            envoy_point(ids[0], 0),
            envoy_point(ids[1], 100),
        ])

        result = module.reconcile(k6, envoy, "runA")

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["matched_events"], 2)
        self.assertFalse(result["runtime_origin_verified"])

    def test_missing_event_fails(self):
        ids = [
            "runA-ddos-vu-1-iter-0",
            "runA-ddos-vu-2-iter-0",
        ]

        k6 = jsonl([k6_point(x, "p01_ddos") for x in ids])
        envoy = jsonl([
            envoy_point(ids[0], 0),
            envoy_point("runA-ddos-vu-3-iter-0", 100),
        ])

        result = module.reconcile(k6, envoy, "runA")

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(result["missing"]), 1)
        self.assertEqual(len(result["unexpected"]), 1)

    def test_workload_mismatch_rejected(self):
        k6 = jsonl([
            k6_point("runA-scraper-vu-1-iter-0", "p01_ddos")
        ])

        with self.assertRaises(ValueError):
            module.parse_k6_p01(k6, "runA")

    def test_foreign_run_rejected(self):
        with self.assertRaises(ValueError):
            module.classify("runB-ddos-vu-1-iter-0", "runA")

    def test_duplicate_json_keys_rejected(self):
        raw = (
            b'{"type":"Point","type":"Point",'
            b'"metric":"nanoclaw_request_manifest"}\n'
        )

        with self.assertRaises(ValueError):
            module.parse_k6_p01(raw, "runA")

    def test_expected_workload_enforced(self):
        ids = [
            "runA-ddos-vu-1-iter-0",
            "runA-ddos-vu-2-iter-0",
        ]

        k6 = jsonl([k6_point(x, "p01_ddos") for x in ids])
        envoy = jsonl([
            envoy_point(ids[0], 0),
            envoy_point(ids[1], 100),
        ])

        with self.assertRaises(ValueError):
            module.reconcile(
                k6, envoy, "runA",
                expected_workload="p01_scraper",
            )

    def test_mixed_workloads_rejected(self):
        ids = [
            ("runA-ddos-vu-1-iter-0", "p01_ddos"),
            ("runA-scraper-vu-1-iter-0", "p01_scraper"),
        ]

        k6 = jsonl([k6_point(x, w) for x, w in ids])
        envoy = jsonl([
            envoy_point(ids[0][0], 0),
            envoy_point(ids[1][0], 100),
        ])

        with self.assertRaises(ValueError):
            module.reconcile(
                k6, envoy, "runA",
                expected_workload="p01_ddos",
            )

    def test_invalid_run_id_rejected(self):
        with self.assertRaises(ValueError):
            module.reconcile(b"{}", b"{}", "../escape")


if __name__ == "__main__":
    unittest.main()
