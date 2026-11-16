"""Offline integration tests: measured Envoy evidence to durable incident."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.durable_offline_incident import IncidentReplayError
from agent.measured_incident_p10 import (
    MeasuredIncidentError,
    evaluate_measured_incident,
    load_measured_report,
)
from chaos.envoy_observer_p09 import write_observation
from chaos.recovery_timeline import evaluate_timeline


def report_for(statuses, experiment_id="p10-integration"):
    events = [
        {
            "time_ms": index * 100,
            "target": "api",
            "status": status,
            "latency_ms": 10,
        }
        for index, status in enumerate(statuses)
    ]

    return {
        "report_version": 1,
        "experiment_id": experiment_id,
        "evidence_source": "isolated_envoy_http",
        "endpoint": "http://testbed-envoy:10000/ready",
        "events": events,
        "healthy_latency_ms": 1000,
        "timeline": evaluate_timeline(events),
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }


class FakeRPC:
    def __init__(self, response=None, failure=None):
        self.calls = 0
        self.response = response or json.dumps({
            "category": "service_failure",
            "target": "api",
            "confidence": 0.9,
            "summary": "Observed HTTP service failure",
            "recommended_action": "investigate_api",
        })
        self.failure = failure

    def call(self, *args, **kwargs):
        self.calls += 1

        if self.failure is not None:
            raise self.failure

        return {"ok": True, "content": self.response}


class MeasuredIncidentTests(unittest.TestCase):

    def _write(self, directory, report):
        evidence_dir = Path(directory) / "evidence"
        evidence_dir.mkdir()

        return write_observation(evidence_dir, report)

    def test_recovery_is_observational_not_agent_attributed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                report_for([503, 200, 200, 200]),
            )
            rpc = FakeRPC()

            result = evaluate_measured_incident(
                rpc, path, Path(directory) / "records"
            )

            self.assertEqual(rpc.calls, 1)
            self.assertEqual(
                result["incident_record"]["result"]["observation_outcome"],
                "SUCCESS",
            )
            self.assertFalse(result["mitigation_executed"])
            self.assertFalse(result["recovery_attributed_to_agent"])
            self.assertFalse(result["production_recovery_verified"])

    def test_regression_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                report_for([503, 200, 200, 200, 503]),
            )

            result = evaluate_measured_incident(
                FakeRPC(), path, Path(directory) / "records"
            )

            self.assertEqual(
                result["incident_record"]["result"]["observation_outcome"],
                "FAILED",
            )

    def test_replay_does_not_call_model_again(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                report_for([503, 200, 200, 200]),
            )
            rpc = FakeRPC()
            output = Path(directory) / "records"

            evaluate_measured_incident(rpc, path, output)

            with self.assertRaises(IncidentReplayError):
                evaluate_measured_incident(rpc, path, output)

            self.assertEqual(rpc.calls, 1)

    def test_uncertain_rpc_does_not_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                report_for([503, 200, 200, 200]),
            )
            rpc = FakeRPC(failure=TimeoutError("uncertain"))
            output = Path(directory) / "records"

            with self.assertRaises(TimeoutError):
                evaluate_measured_incident(rpc, path, output)

            with self.assertRaises(IncidentReplayError):
                evaluate_measured_incident(rpc, path, output)

            self.assertEqual(rpc.calls, 1)

    def test_negative_control_never_calls_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(
                directory,
                report_for([200, 200, 200, 200]),
            )
            rpc = FakeRPC()

            with self.assertRaises(MeasuredIncidentError):
                evaluate_measured_incident(
                    rpc, path, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)

    def test_corrupted_timeline_never_calls_model(self):
        with tempfile.TemporaryDirectory() as directory:
            report = report_for([503, 200, 200, 200])
            report["timeline"]["observation_outcome"] = "FAILED"

            path = Path(directory) / "p10-integration.json"
            path.write_text(json.dumps(report))

            rpc = FakeRPC()

            with self.assertRaises(MeasuredIncidentError):
                evaluate_measured_incident(
                    rpc, path, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p10-integration.json"
            path.write_text(
                '{"experiment_id":"p10-integration",'
                '"experiment_id":"p10-integration"}'
            )

            with self.assertRaises(MeasuredIncidentError):
                load_measured_report(path)

    def test_symlink_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text("{}")

            link = Path(directory) / "p10-integration.json"
            link.symlink_to(source)

            with self.assertRaises(MeasuredIncidentError):
                load_measured_report(link)

    def test_mismatched_filename_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report = report_for([503, 200, 200, 200])
            path = Path(directory) / "wrong-name.json"
            path.write_text(json.dumps(report))

            with self.assertRaises(MeasuredIncidentError):
                load_measured_report(path)


if __name__ == "__main__":
    unittest.main()


class MeasuredIncidentAdditionalTests(unittest.TestCase):

    def test_realistic_initial_failures_then_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_dir = Path(directory) / "evidence"
            evidence_dir.mkdir()

            path = write_observation(
                evidence_dir,
                report_for([503, 503, 503, 200, 200, 200, 200]),
            )

            result = evaluate_measured_incident(
                FakeRPC(), path, Path(directory) / "records"
            )

            self.assertEqual(
                result["observed_sustained_recovery"], "SUCCESS"
            )
            self.assertEqual(
                result["uninterrupted_recovery"], "FAILED"
            )
            self.assertFalse(result["production_recovery_verified"])

    def test_boolean_timeline_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report = report_for([503, 200, 200, 200])

            # Replace a numeric timeline field with a boolean.
            numeric = next(
                key for key, value in report["timeline"].items()
                if type(value) is int and value == 1
            )
            report["timeline"][numeric] = True

            path = Path(directory) / "p10-integration.json"
            path.write_text(json.dumps(report))

            with self.assertRaises(MeasuredIncidentError):
                load_measured_report(path)

    def test_long_experiment_id_rejected_before_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            report = report_for(
                [503, 200, 200, 200],
                experiment_id="a" * 64,
            )

            path = Path(directory) / ("a" * 64 + ".json")
            path.write_text(json.dumps(report))

            rpc = FakeRPC()

            with self.assertRaises(MeasuredIncidentError):
                evaluate_measured_incident(
                    rpc, path, Path(directory) / "records"
                )

            self.assertEqual(rpc.calls, 0)
