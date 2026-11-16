"""Recorded experiment schema and evaluation tests."""

import json
import tempfile
import unittest
from pathlib import Path

from chaos.recorded_experiment import (
    ExperimentError,
    evaluate_experiment,
    load_experiment,
)


def event(time_ms, status, latency=100):
    return {
        "time_ms": time_ms,
        "target": "api",
        "status": status,
        "latency_ms": latency,
    }


def scenario(identifier, kind, statuses):
    return {
        "scenario_id": identifier,
        "kind": kind,
        "events": [
            event(index * 1000, status)
            for index, status in enumerate(statuses)
        ],
    }


class RecordedExperimentTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "experiment.json"

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return self.path

    def experiment(self):
        return {
            "schema_version": 1,
            "experiment_id": "p08-offline",
            "scenarios": [
                scenario("recovery", "service_failure", [503, 200, 200, 200]),
                scenario("regression", "intermittent_failure",
                         [503, 200, 200, 200, 503]),
                scenario("control", "negative_control", [200, 200, 200, 200]),
            ],
        }

    def test_mixed_experiment(self):
        result = evaluate_experiment(self.experiment())
        self.assertEqual(result["scenario_count"], 3)
        self.assertEqual(result["outcome_counts"], {
            "SUCCESS": 1,
            "FAILED": 1,
            "INCONCLUSIVE": 1,
        })
        self.assertFalse(result["mitigation_executed"])

    def test_file_roundtrip(self):
        loaded = load_experiment(self.write(self.experiment()))
        self.assertEqual(loaded["experiment_id"], "p08-offline")

    def test_duplicate_scenario_rejected(self):
        data = self.experiment()
        data["scenarios"][1]["scenario_id"] = "recovery"
        with self.assertRaises(ExperimentError):
            evaluate_experiment(data)

    def test_duplicate_json_key_rejected(self):
        self.path.write_text(
            '{"schema_version":1,"schema_version":1,'
            '"experiment_id":"x","scenarios":[]}',
            encoding="utf-8",
        )
        with self.assertRaises(ExperimentError):
            load_experiment(self.path)

    def test_invalid_timeline_rejected(self):
        data = self.experiment()
        data["scenarios"][0]["events"][1]["status"] = True
        with self.assertRaises(ExperimentError):
            evaluate_experiment(data)

    def test_unexpected_field_rejected(self):
        data = self.experiment()
        data["command"] = "shutdown"
        with self.assertRaises(ExperimentError):
            evaluate_experiment(data)

    def test_negative_control_cannot_claim_recovery(self):
        data = self.experiment()
        data["scenarios"][2]["events"][0]["status"] = 503
        with self.assertRaises(ExperimentError):
            evaluate_experiment(data)

    def test_oversized_file_rejected(self):
        self.path.write_bytes(b" " * (1024 * 1024 + 1))
        with self.assertRaises(ExperimentError):
            load_experiment(self.path)


if __name__ == "__main__":
    unittest.main()
