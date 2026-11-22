"""Offline unit tests for the P01 Envoy collector."""

import unittest
from unittest.mock import patch

from testbed.experiments import collect_p01_envoy as collector


class TestP01EnvoyCollector(unittest.TestCase):

    def test_selects_matching_run(self):
        logs = (
            b'{"request_id":"run123-vu-1"}\n'
            b'{"request_id":"other-vu-1"}\n'
        )

        result = collector.select_records(logs, "run123")

        self.assertEqual(
            result,
            b'{"request_id":"run123-vu-1"}\n',
        )

    def test_rejects_oversized_logs(self):
        logs = b"x" * (collector.MAX_LOG_BYTES + 1)

        with self.assertRaises(ValueError):
            collector.select_records(logs, "run123")

    def test_rejects_oversized_record(self):
        logs = (
            b'{"request_id":"run123-' +
            b"x" * 4096 +
            b'"}\n'
        )

        with self.assertRaises(ValueError):
            collector.select_records(logs, "run123")

    def test_invalid_run_id_rejected_before_docker(self):
        with patch.object(collector, "read_logs") as mock_logs:
            with self.assertRaises(ValueError):
                collector.collect(
                    "../invalid",
                    "missing-k6.json",
                    "output.json",
                )

            mock_logs.assert_not_called()

    def test_invalid_timeout_rejected_before_docker(self):
        with patch.object(collector, "read_logs") as mock_logs:
            with self.assertRaises(ValueError):
                collector.collect(
                    "run123",
                    "missing-k6.json",
                    "output.json",
                    timeout=0,
                )

            mock_logs.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TestP01CollectorReconciliation(unittest.TestCase):
    """End-to-end collector tests using mocked Docker evidence."""

    @staticmethod
    def make_k6_record(request_id):
        return {
            "type": "Point",
            "metric": "nanoclaw_request_manifest",
            "data": {
                "value": 1,
                "tags": {
                    "request_id": request_id,
                    "workload": "p01_ddos",
                },
            },
        }

    @staticmethod
    def make_envoy_record(request_id, offset=0):
        return {
            "timestamp": "2026-01-01T00:00:{:02d}.{:03d}+00:00".format(offset // 1000, offset % 1000),
            "client_ip": "192.0.2.10",
            "method": "GET",
            "path": "/api/data",
            "status": 200,
            "duration_ms": 10,
            "user_agent": "NanoClaw-Test/1.0",
            "request_id": request_id,
        }

    @staticmethod
    def jsonl(records):
        import json

        return (
            "\n".join(json.dumps(row) for row in records) + "\n"
        ).encode("utf-8")

    def setUp(self):
        import tempfile
        from pathlib import Path

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        root = Path(self.directory.name)

        self.k6_path = root / "k6.jsonl"
        self.output_path = root / "envoy.jsonl"

        self.first_id = "runA-ddos-vu-1-iter-0"
        self.second_id = "runA-ddos-vu-2-iter-0"

        self.k6_path.write_bytes(
            self.jsonl([
                self.make_k6_record(self.first_id),
                self.make_k6_record(self.second_id),
                self.make_k6_record("runA-ddos-vu-3-iter-0"),
            ])
        )

    def test_collection_passes_remaining_deadline_to_reader(self):
        with patch.object(
            collector.time,
            "monotonic",
            side_effect=[100.0, 100.75, 101.1],
        ):
            with patch.object(
                collector,
                "read_logs",
                return_value=b"",
            ) as mock_logs:
                with self.assertRaises(TimeoutError):
                    collector.collect(
                        "runA",
                        self.k6_path,
                        self.output_path,
                        timeout=1,
                    )

        self.assertEqual(mock_logs.call_count, 1)
        passed_timeout = mock_logs.call_args.kwargs["timeout"]

        self.assertAlmostEqual(passed_timeout, 0.25)
        self.assertFalse(self.output_path.exists())

    def test_complete_evidence_is_saved(self):
        self.k6_path.write_bytes(
            self.jsonl([
                self.make_k6_record(self.first_id),
                self.make_k6_record(self.second_id),
            ])
        )
        logs = self.jsonl([
            self.make_envoy_record(self.first_id),
            self.make_envoy_record(self.second_id, 100),
        ])

        with patch.object(collector, "read_logs", return_value=logs):
            count = collector.collect(
                "runA",
                self.k6_path,
                self.output_path,
                timeout=1,
            )

        self.assertEqual(count, 2)
        self.assertEqual(self.output_path.read_bytes(), logs)

    def test_duplicate_envoy_id_is_rejected(self):
        logs = self.jsonl([
            self.make_envoy_record(self.first_id),
            self.make_envoy_record(self.first_id, 100),
        ])

        with patch.object(collector, "read_logs", return_value=logs):
            with self.assertRaisesRegex(
                ValueError,
                "duplicate Envoy request IDs",
            ):
                collector.collect(
                    "runA",
                    self.k6_path,
                    self.output_path,
                    timeout=1,
                )

        self.assertFalse(self.output_path.exists())

    def test_unexpected_envoy_id_is_rejected(self):
        logs = self.jsonl([
            self.make_envoy_record(self.first_id),
            self.make_envoy_record("runA-ddos-vu-4-iter-0", 100),
        ])

        with patch.object(collector, "read_logs", return_value=logs):
            with self.assertRaisesRegex(
                ValueError,
                "unexpected Envoy request IDs",
            ):
                collector.collect(
                    "runA",
                    self.k6_path,
                    self.output_path,
                    timeout=1,
                )

        self.assertFalse(self.output_path.exists())

    def test_incomplete_evidence_times_out(self):
        logs = self.jsonl([
            self.make_envoy_record(self.first_id),
            self.make_envoy_record(self.second_id, 100),
        ])

        with patch.object(collector, "read_logs", return_value=logs):
            with patch.object(
                collector.time,
                "monotonic",
                side_effect=[0.0, 0.25, 0.5, 2.0],
            ):
                with self.assertRaisesRegex(
                    TimeoutError,
                    "Envoy evidence incomplete",
                ):
                    collector.collect(
                        "runA",
                        self.k6_path,
                        self.output_path,
                        timeout=1,
                    )

        self.assertFalse(self.output_path.exists())


def test_collector_waits_for_initial_single_record():
    """One valid partial record should not abort evidence polling."""

    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    import json

    from testbed.experiments import collect_p01_envoy as collector

    def jsonl(records):
        return (
            "\n".join(json.dumps(record) for record in records) + "\n"
        ).encode("utf-8")

    def envoy_record(request_id, timestamp):
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

    ids = [
        "runA-ddos-vu-1-iter-0",
        "runA-ddos-vu-2-iter-0",
    ]

    manifest = jsonl([
        {
            "type": "Point",
            "metric": "nanoclaw_request_manifest",
            "data": {
                "value": 1,
                "tags": {
                    "request_id": request_id,
                    "workload": "p01_ddos",
                },
            },
        }
        for request_id in ids
    ])

    first = envoy_record(ids[0], "2026-01-01T00:00:00+00:00")
    second = envoy_record(ids[1], "2026-01-01T00:00:00.100+00:00")

    partial = jsonl([first])
    complete = jsonl([first, second])

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        k6_path = root / "k6.jsonl"
        output_path = root / "envoy.jsonl"

        k6_path.write_bytes(manifest)

        with patch.object(
            collector,
            "read_logs",
            side_effect=[partial, complete],
        ) as mock_logs:
            with patch.object(collector.time, "sleep"):
                count = collector.collect(
                    "runA",
                    k6_path,
                    output_path,
                    timeout=5,
                )

        assert mock_logs.call_count == 2
        assert count == 2
        assert output_path.read_bytes() == complete
