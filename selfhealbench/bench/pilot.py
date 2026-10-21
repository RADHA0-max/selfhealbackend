"""Offline-first SelfHealBench integration. No container or fault-control capability."""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

from integration.nanoclaw_adapter import NanoClawBenchAdapter
from selfhealbench.bench.telemetry import probe_snapshot

SERVICES = frozenset(('api', 'db', 'worker', 'auth'))
ACTIONS = frozenset(('clear_fault', 'start_container', 'no_op', 'escalate'))
FIELDS = frozenset(('root_cause', 'action', 'target', 'reason'))


def validate(plan):
    if not isinstance(plan, dict) or set(plan) != FIELDS:
        raise ValueError('exactly four diagnosis fields required')
    if any(not isinstance(v, str) or not v.strip() for v in plan.values()):
        raise ValueError('nonempty string fields required')
    if len(plan['reason']) > 500:
        raise ValueError('reason exceeds 500 characters')
    if plan['root_cause'] not in SERVICES | {'none', 'unknown'}:
        raise ValueError('invalid root cause')
    if plan['action'] not in ACTIONS:
        raise ValueError('action not allowlisted')
    if plan['action'] in ('clear_fault', 'start_container'):
        if plan['target'] not in SERVICES or plan['root_cause'] != plan['target']:
            raise ValueError('recovery requires a matching service root and target')
    elif plan['target'] != 'none':
        raise ValueError('no_op/escalate requires target none')
    if plan['action'] == 'no_op' and plan['root_cause'] != 'none':
        raise ValueError('no_op requires healthy root')
    return plan


def prepare_evidence(raw, secrets=()):
    """Allowlist pre-incident telemetry; never forward scenario labels or control data.

    Callers must supply deployment secrets for literal redaction. Free-form telemetry
    still requires a label-leakage audit before blind RCA claims.
    """
    if not isinstance(raw, dict):
        raise ValueError('evidence must be an object')
    private_keys = {'authorization', 'api_key', 'apikey', 'password', 'secret',
                    'token', 'bench_token', 'cookie', 'set-cookie'}
    label_keys = {'scenario_id', 'scenario_name', 'ground_truth', 'expected_root',
                  'expected_action', 'injection', 'fault', 'delay_ms'}

    def scrub(value, depth=0):
        if depth > 16:
            raise ValueError('evidence nesting exceeds limit')
        if isinstance(value, dict):
            if len(value) > 1000:
                raise ValueError('evidence object exceeds limit')
            return {key: '[REDACTED]' if key.lower() in private_keys else scrub(item, depth + 1)
                    for key, item in value.items()
                    if isinstance(key, str) and key.lower() not in label_keys}
        if isinstance(value, list):
            if len(value) > 1000:
                raise ValueError('evidence list exceeds limit')
            return [scrub(item, depth + 1) for item in value]
        if isinstance(value, str):
            for secret in secrets:
                if secret:
                    value = value.replace(secret, '[REDACTED]')
            value = re.sub(r'(?i)\b(authorization|api[_-]?key|password|token|secret)'
                           r'\s*[:=]\s*(?:bearer\s+)?[^\s,;]+', r'\1=[REDACTED]', value)
            value = re.sub(r'(?i)\bbearer\s+[a-z0-9._~+/=-]+', 'Bearer [REDACTED]', value)
        return value

    selected = {k: scrub(raw.get(k, {} if k != 'docker_logs' else ''))
                for k in ('probes', 'prometheus', 'docker_logs')}
    selected['docker_logs'] = str(selected['docker_logs'])[-8000:]
    text = json.dumps(selected, allow_nan=False)
    for secret in secrets:
        if secret:
            text = text.replace(json.dumps(secret)[1:-1], '[REDACTED]')
    if len(text.encode()) > 48 * 1024:
        raise ValueError('evidence exceeds 48 KiB')
    return json.loads(text)


class EvidenceCollector:
    """Invoke caller-supplied read-only telemetry readers; no endpoint defaults.

    Readers must bound their own I/O duration and bytes. Failed readers are recorded
    as unavailable, never replaced with healthy telemetry.
    """
    def __init__(self, readers, secrets=()):
        if set(readers) - {'probes', 'prometheus', 'docker_logs'}:
            raise ValueError('unknown telemetry reader')
        self.readers, self.secrets = readers, secrets

    def collect(self):
        raw, errors = {}, {}
        for name, reader in self.readers.items():
            try:
                raw[name] = reader()
            except Exception:
                errors[name] = 'reader failed'  # exception messages may contain secrets
        return {'evidence': prepare_evidence(raw, self.secrets), 'errors': errors}


class NanoClawAgent:
    """Use the real agent transport, never a direct LLM/broker substitution.

    Calling diagnose submits work to NanoClaw. Only use an operator-approved,
    tool-restricted diagnostic session; prompt instructions cannot enforce isolation.
    """
    def __init__(self, transport, secrets=()):
        self.adapter = NanoClawBenchAdapter(transport, instructions=(
            "Benchmark contract overrides the healthy action example: use no_op, not none. "
            "root_cause must be api, db, worker, auth, none or unknown. "
            "action must be clear_fault, start_container, no_op or escalate. "
            "target must be api, db, worker, auth or none. "
            "Recovery target must equal root_cause; no_op/escalate target is none. "
            "Use root_cause none for no_op. reason must be at most 500 characters."))
        self.secrets = secrets

    def diagnose(self, evidence):
        return validate(self.adapter.diagnose(prepare_evidence(evidence, self.secrets)))


def healthy(probes, max_latency_ms=2000):
    if not isinstance(probes, dict) or set(probes) != SERVICES:
        return False
    for service, p in probes.items():
        if not isinstance(p, dict) or type(p.get('status')) is not int or p['status'] != 200:
            return False
        body = p.get('body')
        latency = p.get('latency_ms')
        if not isinstance(body, dict) or body.get('service') != service or body.get('status') != 'ok':
            return False
        if type(latency) not in (float, int) or not math.isfinite(latency) or not 0 <= latency <= max_latency_ms:
            return False
    return True


def verify(probe, timeout=20, interval=2, required=3, clock=time.monotonic, sleep=time.sleep):
    if (type(timeout) not in (int, float) or type(interval) not in (int, float)
            or not math.isfinite(timeout) or not math.isfinite(interval)
            or timeout <= 0 or interval <= 0 or type(required) is not int or required < 2):
        raise ValueError('positive timing and at least two successful samples required')
    started = clock()
    deadline, streak, history = started + timeout, 0, []
    while clock() < deadline:
        try:
            snapshot = probe_snapshot(probe())
            ok = healthy(snapshot)
        except Exception:
            snapshot, ok = {}, False
        # A response arriving after the deadline cannot establish recovery.
        if clock() >= deadline:
            break
        history.append({'ok': ok, 'elapsed_seconds': clock() - started, 'probes': snapshot})
        streak = streak + 1 if ok else 0
        if streak >= required:
            return {'recovered': True, 'history': history}
        sleep(min(interval, max(0, deadline - clock())))
    return {'recovered': False, 'history': history}


def evaluate(scenarios, records, agent):
    """Replay recorded pre-action evidence. Recovery is never inferred from a plan."""
    results = []
    for scenario in scenarios:
        record = records.get(scenario['id'])
        result = {'scenario_id': scenario['id'], 'mode': 'offline_replay',
                  'recovery_success': None, 'executed': False}
        if record is None:
            result.update(status='missing', rca_correct=False, action_correct=False, target_correct=False)
        else:
            try:
                plan = validate(agent.diagnose(prepare_evidence(record['before'])))
                result.update(status='ok', plan=plan,
                              rca_correct=plan['root_cause'] == scenario['expected_root'],
                              action_correct=plan['action'] == scenario['expected_action'],
                              target_correct=plan['target'] == scenario['expected_root'])
            except Exception:
                result.update(status='agent_error', rca_correct=False, action_correct=False, target_correct=False)
        results.append(result)
    denominator = len(scenarios)
    return {'mode': 'offline_replay', 'requested': denominator,
            'completed': sum(r['status'] == 'ok' for r in results),
            'scores': {k: sum(r[k] for r in results) / denominator if denominator else None
                       for k in ('rca_correct', 'action_correct', 'target_correct')},
            'recovery_success': None, 'results': results}


def main():
    parser = argparse.ArgumentParser(description='Offline recorded-decision evaluation; performs no live operations')
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    scenarios = json.loads((Path(__file__).parents[1] / 'scenarios/pilot.json').read_text())
    records = json.loads(args.records.read_text())

    # Per-case agent sees telemetry only; the lookup stays in the harness.
    results = []
    for scenario in scenarios:
        record = records.get(scenario['id'])
        class Agent:
            def diagnose(self, evidence):
                return record['plan']
        results.extend(evaluate([scenario], records, Agent())['results'])
    report = {'mode': 'recorded_decision_replay', 'requested': len(scenarios),
              'completed': sum(r['status'] == 'ok' for r in results),
              'recovery_success': None, 'results': results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
