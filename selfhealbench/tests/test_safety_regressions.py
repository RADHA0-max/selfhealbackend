import copy
import unittest
from unittest.mock import Mock, patch

from selfhealbench.bench.live import IsolatedBackend, run_live, validate_approvals
from selfhealbench.bench.run import load_scenarios
from selfhealbench.bench.scoring import summarize, verified_history
from test_runner import approved_config


class SafetyRegressions(unittest.TestCase):
    def test_shared_identity_missing_or_alias_rejected(self):
        for identity in (None, '', 'test-daemon'):
            config = approved_config()
            config['shared_daemon_id'] = identity
            with self.assertRaises(ValueError):
                validate_approvals(config)

    def test_canonical_shared_socket_rejected(self):
        config = approved_config()
        config['docker_endpoint'] = 'unix:///tmp/../var/run/docker.sock'
        with self.assertRaises(ValueError):
            validate_approvals(config)

    def test_missing_router_blocks_campaign_and_direct_mutations(self):
        backend = IsolatedBackend(approved_config(), 'fixture-token-123456')
        scenario = load_scenarios()[0]
        plan = dict(root_cause='db', target='db', action='clear_fault', reason='fixture')
        with patch.object(backend, '_docker') as docker, patch.object(backend, '_http') as http:
            for operation in (lambda: backend.authorize_scenarios([scenario]),
                              lambda: backend.inject(scenario), lambda: backend.execute(plan), backend.cleanup):
                with self.assertRaisesRegex(ValueError, 'Router integration'):
                    operation()
            docker.assert_not_called()
            http.assert_not_called()

    def test_hostile_healthy_control_plan_never_reaches_executor(self):
        backend = Mock()
        backend.assert_ready = Mock()
        backend.verify.return_value = {'recovered': True}
        backend.evidence.return_value = {'evidence': {'probes': {
            s: {'status': 200, 'body': {'service': s, 'status': 'ok'}, 'latency_ms': 1}
            for s in ('api', 'db', 'worker', 'auth')}}}
        agent = Mock()
        agent.diagnose.return_value = dict(root_cause='db', target='db', action='clear_fault', reason='hostile')
        result = run_live([load_scenarios()[-1]], agent, backend)
        backend.execute.assert_not_called()
        backend.cleanup.assert_not_called()
        self.assertEqual(result['invalid_decisions'], 1)

    def test_verification_history_must_be_consecutive_and_within_deadline(self):
        valid = {'recovered': True, 'history': [{'ok': True, 'elapsed_seconds': n} for n in (0, 2, 4)]}
        self.assertTrue(verified_history(valid))
        for mutate in (lambda v: v['history'].pop(),
                       lambda v: v['history'][1].update(ok=False),
                       lambda v: v['history'][2].update(elapsed_seconds=21),
                       lambda v: v['history'][2].update(elapsed_seconds=float('nan'))):
            value = copy.deepcopy(valid); mutate(value)
            self.assertFalse(verified_history(value))

    def test_cleanup_and_telemetry_required_for_recovery_score(self):
        scenario = load_scenarios()[0]
        history = {'recovered': True, 'history': [{'ok': True, 'elapsed_seconds': n} for n in (0, 2, 4)]}
        record = dict(status='ok', baseline_verified=True, injection_ok=True, fault_observed=True,
                      recovery_verified=True, baseline=history, verification=history, cleanup='verified',
                      plan=dict(root_cause='db', target='db', action='clear_fault', reason='fixture'),
                      before={'evidence': {'probes': {s: {} for s in ('api','db','worker','auth')},
                                           'docker_logs': 'fixture', 'prometheus': {'up': 1}}})
        self.assertEqual(summarize([scenario], {scenario['id']: record}, 'live')['recovery_success'], 1)
        for mutate in (lambda r: r.pop('cleanup'), lambda r: r.update(cleanup='failed'),
                       lambda r: r['before'].update(collection_errors=['tempo']),
                       lambda r: r.pop('verification'), lambda r: r.update(rollback='failed')):
            value = copy.deepcopy(record); mutate(value)
            self.assertEqual(summarize([scenario], {scenario['id']: value}, 'live')['recovery_success'], 0)
