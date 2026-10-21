from selfhealbench.bench.demo import MockBackend
import json
import unittest
from unittest.mock import patch

from selfhealbench.bench.agents import DeterministicAgent, DirectLLMAgent
from selfhealbench.bench.live import IsolatedBackend, run_live, validate_approvals
from selfhealbench.bench.run import load_scenarios, replay
from selfhealbench.bench.scoring import summarize


def approved_config():
    """Fictional configuration, never an actual operator grant."""
    return {"approvals": {name: True for name in
            ("campus_allocation", "network", "ports", "isolated_context",
             "deployment", "fault_injection", "recovery")},
            "operator": "unit-test-only", "docker_context": "test-isolated",
            "docker_endpoint": "unix:///tmp/test-only-docker.sock", "daemon_id": "test-daemon", "shared_daemon_id": "fixture-shared-daemon",
            "project": "selfhealbench-pilot", "network": "selfhealbench-pilot-review",
            "approved_scenarios": ["SHB-001", "SHB-010"],
            "bind_address": "127.0.0.1", "ipv6": False, "internal": True,
            "candidate": "10.250.30.0/26", "gateway": "10.250.30.1",
            "host_ports": dict(api=18080, db=18081, worker=18082, auth=18083,
                               prometheus=19090, loki=13100, tempo=13200),
            "inventory": {
                "complete": {k: True for k in ("host", "routes", "rules", "docker", "vpn")},
                "host_cidrs": [], "route_cidrs": [], "docker_cidrs": [],
                "vpn_cidrs": [], "institutional_cidrs": [],
                "campus_allocation": {"candidate": "10.250.30.0/26", "confirmed": True,
                                      "authority": "fictitious unit-test allocation"}}}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.scenarios = load_scenarios()
        self.plan = dict(root_cause="db", action="clear_fault", target="db", reason="HTTP failure")

    def test_ten_scenarios_missing_in_denominator(self):
        report = summarize(self.scenarios, {"SHB-001": {"status": "ok", "plan": self.plan}})
        self.assertEqual(report["scores"]["rca_correct"], .1)
        self.assertEqual(len(report["missing_scenarios"]), 9)
        self.assertIsNone(report["recovery_success"])

    def test_invalid_timeout_and_failure_counts(self):
        report = summarize(self.scenarios, {
            "SHB-001": {"status": "ok", "plan": {"action": "shell"}},
            "SHB-002": {"status": "timeout"},
            "SHB-003": {"status": "failed", "plan": self.plan}})
        self.assertEqual(report["invalid_decisions"], 1)
        self.assertEqual(report["timeouts"], 1)
        self.assertEqual(report["failures"], 3)
        self.assertEqual(report["scores"]["rca_correct"], 0)

    def test_recovery_requires_all_evidence(self):
        record = {"status": "ok", "plan": self.plan, "recovery_verified": True,
                  "recovery_seconds": 2}
        report = summarize(self.scenarios, {"SHB-001": record}, mode="live")
        self.assertEqual(report["recovery_success"], 0)
        self.assertEqual(report["latencies"]["recovery_seconds"]["observations"], 0)
        record.update(baseline_verified=True, injection_ok=True, fault_observed=True)
        self.assertEqual(summarize(self.scenarios, {"SHB-001": record}, mode="live")["recovery_success"], 0)
        history = {"recovered": True, "history": [
            {"ok": True, "elapsed_seconds": n, "probes": MockBackend().probe()} for n in (0, 2, 4)]}
        record.update(baseline=history, verification=history, cleanup="verified",
                      before=MockBackend().evidence())
        report = summarize(self.scenarios, {"SHB-001": record}, mode="live")
        self.assertEqual(report["recovery_success"], .1)

    def test_benign_unnecessary_intervention(self):
        report = summarize(self.scenarios, {"SHB-010": {"status": "ok", "plan": self.plan}})
        self.assertEqual(report["unnecessary_intervention"]["count"], 1)

    def test_default_replay_uses_only_before_evidence(self):
        outer = self
        class Agent:
            def diagnose(self, evidence):
                outer.assertNotIn("ground_truth", evidence)
                return outer.plan
        result = replay(self.scenarios, {"SHB-001": {"before": {}, "ground_truth": "db"}}, Agent())
        self.assertEqual(result["completed"], 1)
        self.assertIsNone(result["recovery_success"])

    def test_deterministic_and_direct_llm_modes_preserved(self):
        evidence = {"probes": {name: {"status": 200} for name in ("api", "db", "worker", "auth")}}
        self.assertEqual(DeterministicAgent().diagnose(evidence)["action"], "no_op")
        with self.assertRaises(ValueError):
            DirectLLMAgent("http://127.0.0.1:1/v1/chat/completions", "fast")

    def test_independent_approvals_required_before_any_docker_call(self):
        for key in approved_config()["approvals"]:
            config = approved_config(); config["approvals"][key] = False
            with patch("subprocess.run") as runner, self.assertRaises(ValueError):
                IsolatedBackend(config, "unit-test-token-12345")
            runner.assert_not_called()

    def test_shared_context_or_socket_rejected(self):
        for update in ({"docker_context": "default"},
                       {"docker_endpoint": "unix:///var/run/docker.sock"},
                       {"network": "selfheal-inference-v2"}):
            config = approved_config(); config.update(update)
            with self.assertRaises(ValueError):
                validate_approvals(config)

    def test_target_validation_before_recovery(self):
        backend = IsolatedBackend(approved_config(), "unit-test-token-12345")
        with patch.object(backend, "_docker") as docker, self.assertRaises(ValueError):
            backend.execute(dict(self.plan, target="broker"))
        docker.assert_not_called()

    def test_cleanup_failure_stops_campaign(self):
        class Backend:
            def authorize_scenarios(self, scenarios): pass
            def assert_ready(self): pass
            def telemetry_ready(self): return {}
            def verify(self): return {"recovered": True}
            def inject(self, scenario): pass
            def evidence(self):
                return {"evidence": {"probes": {s: {"status": 503}
                        for s in ("api", "db", "worker", "auth")}}}
            def execute(self, plan): return {"executed": True}
            def cleanup(self): raise RuntimeError("fixture cleanup failure")
        outer = self
        class Agent:
            def diagnose(self, evidence): return outer.plan
        report = run_live(self.scenarios, Agent(), Backend())
        self.assertEqual(len(report["records"]), 1)
        self.assertEqual(report["failures"], 1)
        self.assertEqual(len(report["missing_scenarios"]), 9)

    def test_campaign_cannot_exceed_approved_scenarios(self):
        backend = IsolatedBackend(approved_config(), "unit-test-token-12345")
        with patch.object(backend, "_docker") as docker, self.assertRaises(ValueError):
            backend.authorize_scenarios(self.scenarios)
        docker.assert_not_called()

    def test_shared_daemon_under_alias_is_rejected(self):
        config = approved_config()
        backend = IsolatedBackend(config, "unit-test-token-12345")
        with patch.object(backend, "_docker", side_effect=[
                config["docker_endpoint"], config["daemon_id"], "unrelated-container-id", ""]) as docker:
            with self.assertRaisesRegex(ValueError, "outside the isolated benchmark"):
                backend._environment()
        self.assertEqual(docker.call_count, 4)

    def test_safe_http_reader_handles_approved_loopback(self):
        backend = IsolatedBackend(approved_config(), "unit-test-token-12345")
        with patch("urllib.request.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b'{"service":"db","status":"ok"}'
            self.assertEqual(backend._http("db", "/work")["status"], 200)
            request = opener.return_value.open.call_args[0][0]
            self.assertEqual(request.full_url, "http://127.0.0.1:18081/work")


    def test_healthy_control_never_cleans_or_recovers(self):
        from unittest.mock import Mock
        backend = Mock()
        backend.assert_ready = Mock()
        backend.verify.return_value = {"recovered": True}
        backend.evidence.return_value = {"evidence": {"probes": {
            s: {"status": 200, "body": {"service": s, "status": "ok"}, "latency_ms": 1}
            for s in ("api", "db", "worker", "auth")}}}
        backend.execute.return_value = {"executed": False, "action": "no_op"}
        agent = Mock()
        agent.diagnose.return_value = dict(root_cause="none", action="no_op", target="none", reason="healthy")
        report = run_live([self.scenarios[-1]], agent, backend)
        self.assertEqual(report["completed"], 1)
        backend.cleanup.assert_not_called()
        self.assertEqual(report["unnecessary_intervention"]["rate"], 0)

    def test_readiness_failure_prevents_injection(self):
        from unittest.mock import Mock
        backend = Mock()
        backend.assert_ready = Mock()
        backend.telemetry_ready.side_effect = RuntimeError("unavailable")
        result = run_live(self.scenarios[:1], Mock(), backend)
        backend.inject.assert_not_called()
        backend.cleanup.assert_not_called()
        self.assertEqual(result["failures"], 1)

    def test_attempts_and_telemetry_accounting(self):
        report = summarize(self.scenarios, {"SHB-001": {"status": "timeout", "before": {
            "collection_errors": ["tempo:search"], "evidence": {}}}})
        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["skipped"], 9)
        self.assertEqual(report["telemetry_failures"], 1)
        self.assertEqual(report["evidence_completeness"]["complete"], 0)
        self.assertIsNone(report["unnecessary_intervention"]["rate"])
