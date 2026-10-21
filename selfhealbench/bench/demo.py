"""Synthetic, in-memory demonstration. No Docker, HTTP, or live inference."""
import argparse
import json
from pathlib import Path

from selfhealbench.bench.live import run_live
from selfhealbench.bench.pilot import SERVICES, validate, verify
from selfhealbench.bench.run import load_scenarios


class MockBackend:
    def __init__(self):
        self.fault = None
        self.audit = []

    def authorize_scenarios(self, scenarios):
        self.audit.append({'event': 'mock_scope', 'scenarios': [s['id'] for s in scenarios]})

    def assert_ready(self): pass

    def telemetry_ready(self): return {'mock': True}

    def probe(self):
        probes = {s: {'status': 200, 'body': {'service': s, 'status': 'ok'}, 'latency_ms': 1}
                  for s in SERVICES}
        if self.fault and self.fault['fault'] != 'none':
            p = probes[self.fault['target']]
            if self.fault['fault'] == 'latency': p['latency_ms'] = 2600
            else: p['status'] = 0 if self.fault['fault'] == 'stop' else 503
        return probes

    def verify(self):
        ticks = [0]
        return verify(self.probe, clock=lambda: ticks[0],
                      sleep=lambda n: ticks.__setitem__(0, ticks[0] + n))

    def inject(self, scenario):
        self.fault = scenario
        self.audit.append({'event': 'synthetic_fault', 'id': scenario['id']})

    def evidence(self):
        return {'evidence': {'probes': self.probe(), 'docker_logs': 'synthetic service observations',
                             'prometheus': {'up': {'status': 'success', 'data': {
                                 'resultType': 'vector', 'result': [
                                     {'metric': {'__name__': 'up', 'job': 'selfheal-services', 'instance': s + ':8080'},
                                      'value': [1000, '1']} for s in sorted(SERVICES)]}}}},
                'collection_errors': [], 'collected_at': 1000,
                'tempo_search': {'traces': [{'traceID': 'a' * 32, 'rootServiceName': 'selfheal-api',
                                             'startTimeUnixNano': '1000000000000'}]}}

    def execute(self, plan):
        validate(plan)
        # Simulation only; this is not trusted Router authorization.
        self.audit.append({'event': 'mock_execution', 'plan': plan})
        if plan['action'] in ('clear_fault', 'start_container'): self.fault = None
        return {'executed': plan['action'] not in ('no_op', 'escalate'), 'mock': True}

    def cleanup(self):
        self.fault = None
        if not self.verify()['recovered']: raise RuntimeError('mock cleanup failed')
        self.audit.append({'event': 'mock_cleanup_verified'})


class ScriptedAgent:
    def diagnose(self, evidence):
        # This is a deterministic fixture, NOT an AI diagnosis or benchmark result.
        for service, probe in sorted(evidence['probes'].items()):
            if probe['status'] != 200 or probe['latency_ms'] > 2000:
                return dict(root_cause=service, target=service,
                            action='start_container' if probe['status'] == 0 else 'clear_fault',
                            reason='scripted diagnosis of synthetic probe')
        return dict(root_cause='none', target='none', action='no_op', reason='synthetic healthy control')


def demonstrate():
    backend = MockBackend()
    scenarios = load_scenarios()
    report = run_live(scenarios, ScriptedAgent(), backend)
    report['mode'] = 'mock_demonstration'
    report['simulated_recovery_success'] = report.pop('recovery_success')
    report['live_recovery_success'] = None
    for row in report['results']:
        row['simulated_recovery_success'] = row.pop('recovery_success')
    report['audit'] = backend.audit
    report['pending_live_scenarios'] = [s['id'] for s in scenarios]
    report['limitations'] = ['All evidence, diagnoses, execution and elapsed probe times are synthetic.',
                            'Benchmark actions have no trusted Router adapter; live campaigns are blocked.',
                            'Use the integration test for real provider/file-RPC plumbing with mocked HTTP.',
                            'Use Router tests for trusted authorization and durable audit with an in-memory adapter.']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    # Reserve before running; never overwrite another demonstration.
    with args.out.open('x') as output:
        json.dump(demonstrate(), output, indent=2)
        output.write('\n')


if __name__ == '__main__': main()
