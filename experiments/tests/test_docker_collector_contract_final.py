"""Docker-free integration contract tests for the real collector function."""

import hashlib
import inspect
import json
import unittest
from unittest.mock import patch

from experiments.docker_envoy_capture_final import capture_envoy_logs
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class DockerCollectorContractTests(unittest.TestCase):
    def test_validated_evidence_is_reconciled_not_startup_text(self):
        import json
        from datetime import datetime, timedelta, timezone

        from experiments import docker_envoy_capture_final as module
        from experiments.tests.test_envoy_reconciliation_final import fixture

        raw, expected_ids = fixture()
        records = [json.loads(line) for line in raw.splitlines()]

        def timestamp(value):
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(timezone.utc)

        instants = [timestamp(row["timestamp"]) for row in records]
        earliest = min(instants)
        latest = max(instants)

        # Docker capture windows must remain bounded to 600 seconds.
        since_dt = earliest - timedelta(seconds=1)
        until_dt = latest + timedelta(seconds=1)
        self.assertLessEqual(
            (until_dt - since_dt).total_seconds(), 600
        )

        def iso(value):
            return value.isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            )

        since = iso(since_dt)
        until = iso(until_dt)

        def docker_line(instant, payload):
            prefix = iso(instant).encode("ascii")
            return prefix + b" " + payload + b"\n"

        docker_raw = docker_line(
            since_dt + timedelta(milliseconds=1),
            b"Envoy starting",
        )

        for row, line in zip(records, raw.splitlines()):
            docker_raw += docker_line(
                timestamp(row["timestamp"]),
                line,
            )

        docker_raw += docker_line(
            until_dt - timedelta(milliseconds=1),
            b"Envoy ready",
        )

        self.assertTrue(docker_raw.endswith(b"\n"))

        with patch.object(
            module.subprocess,
            "Popen",
        ) as popen, patch.object(
            module,
            "_bounded_read_process",
            return_value=docker_raw,
        ):
            popen.return_value.poll.return_value = 0

            result = module.capture_envoy_logs(
                "nanoclaw-testbed-envoy",
                since=since,
                until=until,
                expected_request_ids=expected_ids,
            )

        self.assertTrue(
            result["request_reconciliation"]["request_ids_match"]
        )
        self.assertEqual(
            result["validated_event_count"],
            len(expected_ids),
        )
        self.assertEqual(
            result["ignored_non_json_messages"],
            2,
        )
        self.assertNotIn("validated_evidence_jsonl", result)
        self.assertFalse(result["runtime_origin_verified"])
    def test_docker_capture_contract_keys(self):
        from experiments import docker_envoy_capture_final as module

        sentinel = {
            "request_reconciliation": {
                "request_ids_match": True,
            },
            "docker_capture_sha256": "a" * 64,
        }

        with patch.object(
            module,
            "_validate_window",
            return_value=(
                "2026-11-16T00:00:00Z",
                "2026-11-16T00:01:00Z",
            ),
        ), patch.object(
            module.subprocess,
            "Popen",
        ) as popen, patch.object(
            module,
            "_bounded_read_process",
            return_value=b"docker-output\n",
        ), patch.object(
            module,
            "normalize_docker_timestamps",
            return_value=b"normalized\n",
        ), patch.object(
            module,
            "extract_envoy_stdout",
            return_value={
                "validated_evidence_jsonl": b"evidence\n",
                "validated_event_count": 2,
            },
        ), patch.object(
            module,
            "reconcile_envoy_jsonl",
            return_value=sentinel["request_reconciliation"],
        ) as reconcile:
            proc = popen.return_value
            proc.poll.return_value = 0

            result = capture_envoy_logs(
                "nanoclaw-testbed-envoy",
                since="2026-11-16T00:00:00Z",
                until="2026-11-16T00:01:00Z",
                expected_request_ids=["run-organic-vu-1-iter-0"],
            )

        reconcile.assert_called_once_with(
            b"evidence\n",
            ["run-organic-vu-1-iter-0"],
        )

        self.assertTrue(
            result["request_reconciliation"]["request_ids_match"]
        )
        self.assertEqual(
            result["docker_capture_sha256"],
            hashlib.sha256(b"docker-output\n").hexdigest(),
        )
        self.assertNotIn("validated_evidence_jsonl", result)
        self.assertFalse(result["runtime_origin_verified"])

    def test_unreconciled_report_cannot_claim_match(self):
        from experiments import docker_envoy_capture_final as module

        with patch.object(
            module,
            "_validate_window",
            return_value=(
                "2026-11-16T00:00:00Z",
                "2026-11-16T00:01:00Z",
            ),
        ), patch.object(
            module.subprocess,
            "Popen",
        ) as popen, patch.object(
            module,
            "_bounded_read_process",
            return_value=b"docker-output\n",
        ), patch.object(
            module,
            "normalize_docker_timestamps",
            return_value=b"normalized\n",
        ), patch.object(
            module,
            "extract_envoy_stdout",
            return_value={
                "validated_evidence_jsonl": b"evidence\n",
                "validated_event_count": 2,
            },
        ), patch.object(
            module,
            "reconcile_envoy_jsonl",
            return_value={"request_ids_match": False},
        ):
            popen.return_value.poll.return_value = 0

            result = capture_envoy_logs(
                "nanoclaw-testbed-envoy",
                since="2026-11-16T00:00:00Z",
                until="2026-11-16T00:01:00Z",
                expected_request_ids=["run-organic-vu-1-iter-0"],
            )

        self.assertFalse(
            result["request_reconciliation"]["request_ids_match"]
        )


if __name__ == "__main__":
    unittest.main()
