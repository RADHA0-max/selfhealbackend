import copy
import json
import unittest
from pathlib import Path

from selfhealbench.bench.pilot import (
    EvidenceCollector, NanoClawAgent, SERVICES, evaluate, healthy,
    prepare_evidence, validate, verify,
)


def probes():
    return {s: {'status': 200, 'body': {'service': s, 'status': 'ok'},
                'latency_ms': 10} for s in SERVICES}


class PilotTests(unittest.TestCase):
    def test_strict_recovery(self):
        self.assertTrue(healthy(probes()))
        for mutate in (
            lambda p: p.clear(), lambda p: p.pop('db'),
            lambda p: p['db'].update(status=503),
            lambda p: p['db'].update(body={}),
            lambda p: p['db'].update(latency_ms=2600),
            lambda p: p['db'].update(latency_ms=float('nan')),
            lambda p: p['db'].pop('latency_ms'),
        ):
            p = probes(); mutate(p)
            self.assertFalse(healthy(p))

    def test_streak_resets(self):
        ticks = [0]
        samples = iter([probes(), {}, probes(), probes(), probes()])
        result = verify(lambda: next(samples), clock=lambda: ticks[0],
                        sleep=lambda n: ticks.__setitem__(0, ticks[0] + n))
        self.assertTrue(result['recovered'])
        self.assertEqual(len(result['history']), 5)

    def test_timeout_and_reader_errors_fail_closed(self):
        ticks = [0]
        def broken():
            raise RuntimeError('secret')
        result = verify(broken, timeout=3, interval=1, clock=lambda: ticks[0],
                        sleep=lambda n: ticks.__setitem__(0, ticks[0] + n))
        self.assertFalse(result['recovered'])
        self.assertNotIn('secret', str(EvidenceCollector({'probes': broken}).collect()))

    def test_evidence_boundary(self):
        result = prepare_evidence({'scenario_id': 'SHB-001', 'ground_truth': 'db',
                                   'docker_logs': 'private secret'}, ['secret'])
        self.assertEqual(set(result), {'probes', 'prometheus', 'docker_logs'})
        self.assertNotIn('secret', str(result))
        self.assertLessEqual(len(prepare_evidence({'docker_logs': 'a'*9000})['docker_logs']), 8000)
        with self.assertRaises(ValueError):
            prepare_evidence({'probes': {'oversize': 'x'*60000}})

    def test_real_adapter_contract(self):
        class Transport:
            def request(self, prompt):
                self.prompt = prompt
                return json.dumps({'root_cause': 'db', 'action': 'clear_fault',
                                   'target': 'db', 'reason': 'HTTP failure'})
        transport = Transport()
        self.assertEqual(NanoClawAgent(transport).diagnose({})['target'], 'db')
        self.assertIn('clear_fault', transport.prompt)
        self.assertIn('no_op, not none', transport.prompt)

    def test_invalid_plans(self):
        plan = {'root_cause': 'db', 'action': 'clear_fault', 'target': 'db', 'reason': 'failed'}
        self.assertEqual(validate(plan), plan)
        for patch in ({'action': 'shell'}, {'target': 'api'}, {'extra': 'x'},
                      {'reason': 'x'*501}, {'action': 'no_op', 'target': 'none'},
                      {'reason': None}):
            with self.assertRaises(ValueError):
                validate(dict(plan, **patch))

    def test_all_ten_cases_and_no_label_leakage(self):
        scenarios = json.loads((Path(__file__).parents[1]/'scenarios/pilot.json').read_text())
        self.assertEqual(len(scenarios), 10)
        for scenario in scenarios:
            plan = {'root_cause': scenario['expected_root'], 'target': scenario['expected_root'],
                    'action': scenario['expected_action'], 'reason': 'fixture decision'}
            class Agent:
                def diagnose(inner, ev):
                    self.assertNotIn('ground_truth', ev)
                    return plan
            report = evaluate([scenario], {scenario['id']: {'before': {'ground_truth': scenario}}}, Agent())
            self.assertEqual(report['scores']['action_correct'], 1)
            self.assertIsNone(report['recovery_success'])
            self.assertFalse(report['results'][0]['executed'])
        report = evaluate(scenarios, {}, Agent())
        self.assertEqual(report['requested'], 10)
        self.assertEqual(report['completed'], 0)
        self.assertEqual(report['scores']['rca_correct'], 0)
