"""Offline archived Envoy verification regression tests."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.verify_archived_envoy_final import verify


class ArchivedEnvoyVerifierTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_id = "offline-test"

        rows = []
        for index, second in enumerate((2, 1)):
            event = {
                "timestamp": (
                    "2026-11-19T04:24:%02d+00:00" % second
                ),
                "client_ip": "172.20.0.5",
                "method": "GET",
                "path": "/health",
                "status": 200,
                "duration_ms": 1,
                "user_agent": "offline-test",
                "request_id": "request-%d" % index,
            }
            rows.append(
                "2026-11-19T04:24:%02d.000000000Z " % (index + 3)
                + json.dumps(event, separators=(",", ":"))
                + "\n"
            )

        self.raw = "".join(rows).encode()

        self.archive = self.root / (
            self.run_id + ".envoy-docker-stdout.log"
        )
        self.manifest = self.root / (
            self.run_id + ".raw-capture-verification.json"
        )
        self.receipt = self.root / (
            self.run_id + ".reserved/envoy-evidence.json"
        )

        self.receipt.parent.mkdir()
        self.archive.write_bytes(self.raw)

        evidence = {
            "run_id": self.run_id,
            "docker_capture_sha256": hashlib.sha256(
                self.raw
            ).hexdigest(),
            "envoy_validated_event_count": 2,
            "request_count": 2,
            "request_ids_match": True,
            "since": "2026-11-19T04:24:00Z",
            "until": "2026-11-19T04:25:00Z",
        }

        self.receipt.write_text(json.dumps(evidence))

        metadata = {
            "run_id": self.run_id,
            "archive_sha256": evidence["docker_capture_sha256"],
            "receipt_sha256": hashlib.sha256(
                self.receipt.read_bytes()
            ).hexdigest(),
            "raw_stdout_records": 2,
            "capture_window": {
                "since": evidence["since"],
                "until": evidence["until"],
            },
        }

        self.manifest.write_text(json.dumps(metadata))

    def test_valid_offline_capture(self):
        result = verify(self.run_id, self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(result["validated_events"], 2)

    def test_reject_tampered_archive(self):
        self.archive.write_bytes(self.raw + b"x")
        with self.assertRaises(ValueError):
            verify(self.run_id, self.root)

    def test_reject_tampered_receipt(self):
        self.receipt.write_text("{}")
        with self.assertRaises(ValueError):
            verify(self.run_id, self.root)

    def test_reject_duplicate_request_ids(self):
        lines = self.raw.decode().splitlines()
        first = json.loads(lines[0].split(" ", 1)[1])
        second = json.loads(lines[1].split(" ", 1)[1])
        second["request_id"] = first["request_id"]
        lines[1] = (
            lines[1].split(" ", 1)[0]
            + " "
            + json.dumps(second)
        )

        modified = ("\n".join(lines) + "\n").encode()
        self.archive.write_bytes(modified)

        evidence = json.loads(self.receipt.read_text())
        evidence["docker_capture_sha256"] = hashlib.sha256(
            modified
        ).hexdigest()
        self.receipt.write_text(json.dumps(evidence))

        metadata = json.loads(self.manifest.read_text())
        metadata["archive_sha256"] = evidence[
            "docker_capture_sha256"
        ]
        metadata["receipt_sha256"] = hashlib.sha256(
            self.receipt.read_bytes()
        ).hexdigest()
        self.manifest.write_text(json.dumps(metadata))

        with self.assertRaises(ValueError):
            verify(self.run_id, self.root)


if __name__ == "__main__":
    unittest.main()
